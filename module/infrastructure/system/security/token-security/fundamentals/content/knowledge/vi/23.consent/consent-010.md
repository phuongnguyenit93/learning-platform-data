# Không dùng consent thay cho authorization policy

## 1. Consent là sự chấp thuận, không phải quyền lực vô hạn

Trong chương **Consent** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này giải thích một nguyên tắc quan trọng khi thiết kế OAuth 2.0/OpenID Connect (OIDC): **việc người dùng nhấn “Đồng ý” trên màn hình consent không tự chứng minh ứng dụng được quyền truy cập một tài nguyên, thực hiện một hành động hay vượt qua giới hạn bảo mật của tổ chức**.

Hãy xét ứng dụng **Expense Viewer** kết nối với hệ thống quản lý chi phí **Company Expenses API**. Alice là nhân viên có quyền **xem** khoản chi của phòng ban mình, nhưng **không có quyền duyệt** chi phí. Ứng dụng yêu cầu:

~~~text
OAuth client: expense-viewer
Requested scopes:
    expenses:read
    expenses:approve

Consent screen:
    Expense Viewer muốn xem và phê duyệt chi phí.
    [Từ chối]    [Đồng ý]
~~~

Alice nhấn **Đồng ý**. Có nên cấp access token có `expenses:approve` và cho Expense Viewer duyệt tất cả khoản chi không?

**Không.** Alice không thể “đồng ý cấp” một quyền nghiệp vụ mà chính Alice không được phép ủy quyền. Authorization Server (AS) phải áp **chính sách cấp quyền/grant policy** khi phát hành token. Resource Server (RS) phải tiếp tục kiểm tra **ai** đang thực hiện **hành động gì** trên **tài nguyên nào** trong **ngữ cảnh nào**.

Ví dụ:

~~~text
Alice:
    quyền nghiệp vụ = expenses:read (phòng ban A)

Ứng dụng:
    có thể yêu cầu = expenses:read, expenses:approve

Alice nhấn Đồng ý:
    chấp thuận yêu cầu chia sẻ dữ liệu trong trải nghiệm consent

Authorization Server:
    KHÔNG cấp expenses:approve cho grant này

Expenses API:
    VẪN từ chối POST /expenses/748/approve nếu Alice thiếu quyền.
~~~

**Consent có thể là điều kiện cần trong một số luồng, nhưng không phải điều kiện đủ để cho phép mọi truy cập.** Ngay cả khi AS phát access token đúng scope, RS vẫn phải kiểm tra policy của hành động và tài nguyên cụ thể.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **user consent**, **client authorization**, **grant policy** và **resource authorization**.
2. Hiểu vì sao màn hình consent, scopes, audience và các claims trong token có vai trò khác nhau.
3. Thiết kế quy trình cấp access token không vượt quyền người dùng, quyền client hoặc chính sách tổ chức.
4. Ngăn **Broken Object Level Authorization (BOLA/IDOR)** dù người dùng đã đồng ý và JWT đã được xác minh.
5. Xử lý tình huống user rút lại consent, bị thu hồi role, chuyển tenant hoặc token còn hạn.
6. Thiết kế policy cho ứng dụng bên thứ ba, tác vụ backend, delegated admin, BFF và microservices.
7. Triển khai các kiểm tra bằng Java/Spring Security, pseudocode và SQL truy vấn theo ownership/tenant.
8. Kiểm thử các đường tăng quyền, consent phishing và sự khác nhau giữa HTTP 401 với 403.

## 2. Bốn khái niệm không được gộp làm một

| Khái niệm | Câu hỏi nó trả lời | Bên chịu trách nhiệm chính |
|---|---|---|
| **Consent** | Người dùng có chấp thuận một hành vi chia sẻ/ủy quyền được trình bày hay không? | Người dùng và giao diện/luồng consent của AS |
| **Client policy** | Ứng dụng này có được dùng grant type, xin những scopes/resources nào? | AS và quản trị client registration |
| **Grant/issuance policy** | Grant thực tế cho subject, client, audience và scope này có hợp lệ tại thời điểm phát token không? | AS, có thể dùng policy engine |
| **Resource authorization** | Principal được phép thực hiện action này trên resource cụ thể này, trong tenant/context hiện tại không? | RS, dịch vụ nghiệp vụ, PDP/PEP |

Ví dụ về bốn lớp:

~~~text
Consent:
    Alice đồng ý Expense Viewer đọc dữ liệu chi phí của mình.

Client policy:
    Expense Viewer chỉ được xin expenses:read ở Expenses API.

Grant policy:
    Alice chỉ được ủy quyền xem dữ liệu trong phòng ban A.

Resource authorization:
    GET /expenses/748 được phép nếu 748 thuộc phòng ban A
    và Alice có quyền xem bản ghi đó.
~~~

Chỉ một trong bốn lớp đạt là **chưa đủ** để cho phép hành động. Nếu user **từ chối consent** cần thiết, không phát grant; nếu user **đồng ý** nhưng client không đủ quyền, vẫn không phát grant ngoài policy; nếu grant hợp lệ mà **resource ngoài quyền**, vẫn từ chối ở API.

### 2.1. Consent không đồng nghĩa authentication

**Authentication** xác minh danh tính đang tương tác, ví dụ Alice đã đăng nhập bằng OP. **Consent** là quyết định về một yêu cầu được trình bày sau hoặc trong quá trình đó.

Một request có thể có trạng thái:

~~~text
Đã xác thực Alice:       YES
Đã hiển thị consent:     YES
Alice nhấn Đồng ý:       YES
Được phép duyệt chi phí: NO
~~~

Một ID token OIDC chứng minh các khẳng định xác thực phù hợp profile dành cho client, nhưng **không phải** bằng chứng Alice có quyền duyệt chi phí. Tương tự, nút “Đồng ý” không thay chữ ký ID token hoặc điều kiện `state`/PKCE của Authorization Code flow.

### 2.2. Consent không phải role, permission hay ACL

- **Role**: ví dụ `EMPLOYEE`, `FINANCE_APPROVER`.
- **Permission**: ví dụ quyền duyệt hóa đơn trong một hạn mức.
- **ACL/ownership**: người dùng nào được đọc hoặc sửa bản ghi cụ thể.
- **Policy theo thuộc tính (ABAC)**: điều kiện tenant, department, resource state, mức tiền, thời gian, risk, actor.
- **Consent**: quyết định chấp thuận một yêu cầu được thông báo theo ngữ cảnh.

Một người **không có quyền** duyệt hóa đơn không thể dùng consent để tự tạo role `FINANCE_APPROVER`. Một người có quyền với dữ liệu của chính mình cũng không tự có quyền cấp ứng dụng truy cập dữ liệu của các đồng nghiệp khác.

### 2.3. Consent kỹ thuật khác consent về quyền riêng tư

Trong OAuth/OIDC, từ **consent** thường chỉ **tương tác ủy quyền** tại AS: user đồng ý cho client truy cập phạm vi đã mô tả. Trong luật về quyền riêng tư/bảo vệ dữ liệu, “consent” có thể là một **cơ sở xử lý dữ liệu** với yêu cầu pháp lý riêng.

Hai điều này **không tự tương đương**. Một màn hình OAuth “Allow” không tự giải quyết mọi nghĩa vụ pháp lý, mục đích xử lý dữ liệu, retention hay cơ sở hợp pháp khác; và có những hoạt động nội bộ được phép theo chính sách mà không yêu cầu một màn hình consent OAuth mỗi lần.

Thiết kế cần sự phối hợp của security, product và privacy/legal khi có dữ liệu cá nhân, thay vì coi OAuth consent receipt như giấy phép sử dụng dữ liệu cho mọi mục đích.

## 3. Mô hình tin cậy từ yêu cầu quyền đến thao tác trên API

OAuth 2.0 tách **Authorization Server** (cấp token) khỏi **Resource Server** (cung cấp dữ liệu). Client và người dùng là hai chủ thể khác nhau, mỗi bên có giới hạn riêng.

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant C as Expense Viewer
    participant AS as Authorization Server
    participant P as Grant Policy
    participant RS as Expenses API
    U->>C: Muốn xem chi phí
    C->>AS: Authorization request: expenses:read + expenses:approve
    AS->>P: Kiểm tra client, subject, scopes, audience
    P-->>AS: Chỉ cho phép expenses:read
    AS-->>U: Hiển thị yêu cầu hợp lệ / giới hạn quyền
    U->>AS: Đồng ý hoặc từ chối
    AS->>P: Xác minh quyết định và grant trước phát token
    P-->>AS: Scope thực tế = expenses:read
    AS-->>C: Access token đúng quyền và audience
    C->>RS: GET /expenses/748, Authorization: Bearer token
    RS->>RS: Validate token, tenant, ownership, action
    RS-->>C: Chỉ trả dữ liệu được phép
    C->>RS: POST /expenses/748/approve
    RS-->>C: 403 nếu thiếu quyền duyệt
~~~

**Sơ đồ là mô hình minh họa.** AS có thể từ chối toàn bộ request vì yêu cầu scope không hợp lệ, hoặc giới hạn scopes được cấp theo contract. Điểm bất biến là **không được cấp quyền ngoài policy** và consent UI phải mô tả trung thực quyền sẽ được cấp.

### 3.1. Tập quyền được cấp phải có ranh giới

Ở mức khái niệm, một AS có thể xem các tập:

~~~text
requestedScopes    = quyền client xin
clientAllowed      = quyền loại client/registration được phép xin
subjectDelegatable = quyền chủ thể thực sự có thể ủy quyền
policyAllowed      = quyền thỏa tổ chức, tenant, resource và context
consented          = quyền user đã chấp thuận, khi consent được yêu cầu

grantedScopes ⊆ requestedScopes
grantedScopes ⊆ clientAllowed
grantedScopes ⊆ subjectDelegatable
grantedScopes ⊆ policyAllowed
grantedScopes ⊆ consented          (nếu consent áp dụng)
~~~

Đây là **mô hình an toàn khái niệm**, không phải một công thức thuật toán bắt buộc cho mọi OAuth flow. Ví dụ với client credentials không có End-User, không tồn tại tập `subjectDelegatable` theo nghĩa user và cũng không có user consent; thay vào đó policy kiểm soát quyền của workload/client.

Một hệ thống có scopes “được phép gọi API” tách biệt business permissions có thể cấp `expenses:read` dựa trên client/consent rồi yêu cầu RS kiểm tra quyền từng khoản chi. Khi đó **scope không phải tập permissions cuối cùng của Alice**. Điều này không phá nguyên tắc: quyền ở RS **không được tăng** chỉ vì scope hoặc consent hợp lệ.

### 3.2. Quyết định cuối cùng không nằm ở consent screen

Mọi lần truy cập resource có thể cần một policy khác:

~~~text
allow(resource, action, principal, context)
    = tokenValidForThisApi
      AND actionAllowedByScopeOrGrant
      AND subjectOrActorAllowedByPolicy
      AND resourceBelongsToPermittedBoundary
      AND currentContextAllowsAction
~~~

Trong Expense API, “current context” có thể gồm:

- Alice có còn là nhân viên phòng ban A không?
- Bản ghi có thuộc đúng tenant/phòng ban không?
- Alice là owner, người được giao xử lý hay được chia sẻ hợp lệ?
- Khoản chi đã duyệt/chốt, không còn được chỉnh sửa?
- Số tiền có vượt hạn mức người duyệt?
- Quyền role/ACL có bị thu hồi sau khi access token được cấp?

Consent **không trả lời** các câu hỏi động này. Chúng thuộc về authorization policy và dữ liệu nghiệp vụ tại nơi thực thi quyền.

## 4. Scope: từ ngữ được hiển thị không phải quyền tuyệt đối

Trong OAuth 2.0, scope biểu diễn phạm vi truy cập mà client xin và AS có thể cấp theo chính sách. `scope=expenses:read` là thông tin hữu ích, nhưng **tên scope không tự định nghĩa quyền trên mọi bản ghi**.

### 4.1. Phân biệt scope và quyết định business

| Scope hoặc yêu cầu | Cho phép xét loại thao tác | Vẫn cần kiểm tra gì? |
|---|---|---|
| `expenses:read` | Có thể gọi API đọc chi phí | Tenant, owner, department, sensitivity |
| `expenses:write` | Có thể gọi API tạo/sửa | Record state, owner, limit, field-level policy |
| `expenses:approve` | Có thể gọi API duyệt | Role approver, hạn mức, separation of duties |
| `contacts:read` | Có thể đọc contact được ủy quyền | Chủ sở hữu contact và purpose cụ thể |
| `orders:read` | Có thể gọi API đọc đơn | Người mua/đại diện và chính sách tenant |
| `admin` | Một scope rất rộng nếu được thiết kế | Không tự làm caller thành admin của mọi tenant |

Tách hai điều kiện:

~~~text
Can call read endpoint?
    -> access token có scope phù hợp?

Can read resource #748?
    -> principal/tenant/ownership/policy có cho phép?
~~~

Một lỗ hổng **BOLA/IDOR** vẫn tồn tại nếu endpoint chỉ check scope rồi lấy record theo `id` từ đường dẫn mà không kiểm tra ownership/tenant.

### 4.2. Không tin scope chỉ vì nằm trong authorization request

Client có thể gửi:

~~~http
GET /oauth2/authorize?response_type=code&client_id=expense-viewer&scope=expenses%3Aread%20expenses%3Aapprove&redirect_uri=<REGISTERED_URI>&state=<STATE>&code_challenge=<CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Đây là yêu cầu **từ client**, không phải lệnh phải cấp mọi scope. AS phải áp chính sách client registration, subject/consent và grant. Nếu scope `expenses:approve` không hợp lệ cho client hoặc user, AS không được phát token chứa scope đó theo một “đường tiện lợi”.

Khi scopes được **giới hạn** thay vì từ chối toàn bộ request, response/UX phải phản ánh **quyền thực sự được cấp**, không khiến user/client tin mọi scope xin ban đầu đều đã được chấp thuận.

### 4.3. Không có scope cũng chưa chứng minh cho phép hay từ chối mọi quyền

Một access token được AS cấp có thể có scope semantics riêng theo profile. Resource Server phải xác minh đúng contract. **Không tự coi thiếu claim `scope` là được phép mọi action**; cũng không tự kết luận OAuth login thành công đồng nghĩa token có mọi scope.

Ví dụ Spring Security có thể ánh xạ scopes thành authorities dạng `SCOPE_expenses:read`, nhưng **authority này chỉ là một điều kiện** của business policy. Cần kiểm tra context và record cụ thể.

## 5. Audience, loại token và issuer: consent không mở rộng đích nhận

Giả sử Alice đã đồng ý Expense Viewer đọc chi phí. AS cấp access token dành cho:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://expenses.example.com"],
  "client_id": "expense-viewer",
  "scope": "expenses:read",
  "iat": 1893492000,
  "exp": 1893492900
}
~~~

Đây chỉ là **JWT payload minh họa**, không phải JWT có chữ ký. Token có audience `https://expenses.example.com` **không được mặc nhiên dùng** tại `https://payments.example.com` hoặc `https://admin.example.com`.

Consent có thể ghi “cho ứng dụng đọc chi phí”; đó không phải giấy phép cho mọi API cùng tổ chức. Resource Server phải kiểm tra:

1. **Issuer** có phải nhà phát hành tin cậy cho API?
2. Token có **chữ ký/thuật toán/khóa** hợp lệ nếu là JWT, hoặc **active state/introspection** đúng contract nếu là opaque token?
3. **Audience** có hướng tới API đang nhận request?
4. Token type/profile, `exp`, `nbf` và các claims bắt buộc có hợp lệ?
5. **Scope và client/grant context** có cho phép loại thao tác được yêu cầu?
6. **Principal/action/resource/tenant** có thỏa policy hiện tại?

### 5.1. Access token, ID token và refresh token không thể hoán đổi

| Token | Dùng cho | Không được coi là |
|---|---|---|
| **Access token** | Resource server đúng `aud` và token profile | Quyền vô hạn chỉ vì người dùng đã consent |
| **ID token** (OIDC) | Client xác minh kết quả đăng nhập | Access token cho Expense API |
| **Refresh token** | AS token endpoint để xin token mới theo grant | Credential trực tiếp đọc dữ liệu API |
| **Authorization code** | Client đổi ở token endpoint theo Authorization Code flow | Bằng chứng user có quyền trên từng record |

Một ID token chứa `sub=alice-123` và `aud=expense-viewer` cho phép client nhận diện subject sau OIDC validation, **không cấp** quyền gọi `POST /expenses/748/approve`.

### 5.2. JWT và opaque access token đều cần policy

Với **JWT**, RS thường xác minh chữ ký và claims offline; JWT đúng chữ ký **không xác nhận** business policy của từng record tại thời điểm hiện tại. Với **opaque access token**, RS thường gọi introspection để xác minh trạng thái và metadata, nhưng **`active=true` cũng chưa đủ** để đọc mọi tài nguyên.

Hai cách trình bày token khác nhau, yêu cầu authorization giống nhau:

~~~text
Token accepted by RS
    |
    v
Scope / role / claims được xác minh
    |
    v
Kiểm tra tenant + owner + action + resource state
    |
    v
ALLOW hoặc DENY
~~~

### 5.3. Không mở rộng audience bằng token exchange tùy tiện

Microservice có thể cần token dành cho dịch vụ downstream. **RFC 8693 Token Exchange** là một cơ chế có thể áp dụng theo profile, nhưng **không có nghĩa** bất kỳ bearer token nào cũng được đổi sang token có audience khác và quyền rộng hơn.

AS/STS phải kiểm tra:

- Client hoặc workload được phép xin token exchange?
- Subject, actor và quan hệ delegation đã được xác minh?
- Resource/audience mới có nằm trong policy?
- Scope mới có vượt quyền chủ thể hoặc phạm vi delegation ban đầu?
- Có cần sender-constrained token hoặc giới hạn TTL?

Consent ban đầu cho Expense Viewer không tự mở thành quyền cấp token `payments:admin` cho một service ở phía sau.

## 6. Object-level authorization và multi-tenant: nơi dễ bị khai thác nhất

Ngay cả access token có `scope=expenses:read`, ứng dụng vẫn cần biết **bản ghi cụ thể** mà request đang hỏi thuộc ai, và caller có được đọc nó không.

### 6.1. Ví dụ BOLA/IDOR

Alice thuộc tenant A, Bob thuộc tenant B. Expense Viewer gọi:

~~~http
GET /api/expenses/748 HTTP/1.1
Host: expenses.example.com
Authorization: Bearer <VALID_ACCESS_TOKEN_FOR_ALICE>
~~~

Giả sử record `748` thuộc tenant B. Code sai:

~~~java
// SAI: có token với scope read thì lấy bản ghi theo ID, không kiểm tenant.
@PreAuthorize("hasAuthority('SCOPE_expenses:read')")
@GetMapping("/api/expenses/{id}")
public ExpenseDto read(@PathVariable long id) {
    return expenseRepository.findById(id)
        .map(ExpenseDto::from)
        .orElseThrow();
}
~~~

Kiểm tra scope có thể đúng, nhưng endpoint vẫn trả dữ liệu của Bob. User đã đồng ý trên consent screen cũng không khiến điều này hợp pháp.

### 6.2. Cần áp ràng buộc trong truy vấn nghiệp vụ

Ví dụ SQL conceptual:

~~~sql
SELECT id, amount, status, owner_id, tenant_id
FROM expenses
WHERE id = :expense_id
  AND tenant_id = :authorized_tenant_id
  AND (
      owner_id = :verified_local_user_id
      OR EXISTS (
          SELECT 1
          FROM expense_shares s
          WHERE s.expense_id = expenses.id
            AND s.grantee_user_id = :verified_local_user_id
            AND s.permission = 'READ'
      )
  );
~~~

Các giá trị `authorized_tenant_id`, `verified_local_user_id` phải được xây từ **principal/session/token đã xác minh và policy**, không lấy trực tiếp từ `X-Tenant-Id` hoặc query do attacker gửi. Query chỉ là một lớp phòng vệ; business service còn phải xét record state và policy khi cần.

**Đừng dùng `tenantId` trong URL để thay hoàn toàn tenant membership check.** User có thể đổi `/tenants/A/expenses/748` thành `/tenants/B/expenses/748`.

### 6.3. Truy vấn “read all” không đồng nghĩa user có thể đọc tất cả

Một scope như `expenses:read` có thể mở **khả năng gọi endpoint list**, nhưng danh sách phải được lọc theo dữ liệu user được xem:

~~~text
GET /api/expenses
    -> chỉ các bản ghi được policy cho phép.

GET /api/expenses/748
    -> kiểm tra id=748 nằm trong phạm vi được phép.

GET /api/expenses/export
    -> export cũng phải áp cùng policy, không dùng data lake bypass.
~~~

Chức năng export, batch API, search, report và background job thường là đường vòng qua object-level authorization nếu chỉ kiểm scope tại controller.

### 6.4. Tách policy theo action

Một khoản chi có thể:

~~~text
owner = Alice
tenant = A
status = SUBMITTED
amount = 9_000_000
~~~

Alice có quyền đọc và có thể sửa khi trạng thái DRAFT, nhưng không nhất thiết được duyệt khoản chi của chính mình. Quy tắc separation of duties có thể là:

~~~text
CanApproveExpense(principal, expense):
    principal.role includes FINANCE_APPROVER
    AND expense.tenant == principal.authorizedTenant
    AND expense.status == SUBMITTED
    AND expense.amount <= principal.approvalLimit
    AND expense.owner != principal.userId
~~~

Ngay cả khi scope `expenses:approve` được cấp đúng, **resource state và separation of duties vẫn là chính sách bắt buộc**, không thể bỏ vì user đã nhấn “Cho phép”.

## 7. Tổ chức, người quản trị và delegated consent

Trong hệ thống doanh nghiệp, có nhiều chủ thể tham gia:

- **Người dùng** như Alice, có thể đồng ý chia sẻ phần dữ liệu mình được phép chia sẻ.
- **Quản trị viên tổ chức**, có thể phê duyệt ứng dụng/scope trên cơ sở **quyền quản trị được cấp thực tế**.
- **Chính sách an ninh/tổ chức**, đặt giới hạn không thể vượt chỉ qua nút consent.
- **Chủ sở hữu tài nguyên**, có thể khác người đang đăng nhập.
- **Resource server**, cưỡng chế quyền ở nơi dữ liệu thực sự tồn tại.

### 7.1. User consent không thay admin authorization

Một ứng dụng bên thứ ba xin đọc toàn bộ email hoặc dữ liệu nhân sự trong tổ chức. Dù Alice bấm đồng ý, Alice có thể không có quyền chia sẻ dữ liệu của đồng nghiệp hoặc dữ liệu quản trị.

~~~text
User Alice:
    allowed: đọc dữ liệu cá nhân được cấp
    not allowed: đọc hồ sơ nhân sự của cả công ty

Client:
    xin organization:hr:read-all

User consent:
    YES

Issuance policy:
    DENY hoặc yêu cầu admin approval có thẩm quyền
~~~

Với **admin consent**, AS/identity platform phải xác minh người phê duyệt có **quyền quản trị cho tenant và scope được yêu cầu**. Không cho một người có role admin của tenant A phê duyệt truy cập tenant B.

### 7.2. Admin approval cũng không được thay resource policy

Ngay cả khi một quản trị viên có thẩm quyền đã phê duyệt client:

- Ứng dụng vẫn phải xác thực với AS đúng registration.
- Access token chỉ có scopes/audience và TTL được cấp.
- Những record bị hạn chế theo quy định nghiệp vụ, legal hold, data classification hoặc segregation of duties vẫn có thể bị chặn.
- Người dùng/nhân viên không tự có role mới từ sự kiện admin duyệt ứng dụng.

**Admin consent có thể cấp quyền cho một loại ứng dụng hoặc phạm vi trong tổ chức khi policy cho phép, nhưng không đồng nghĩa bỏ tất cả kiểm soát tại resource server.**

### 7.3. Không đồng nhất người dùng, client và service principal

Một delegated access token có thể đại diện cho yêu cầu **thay mặt người dùng**, trong khi client credentials token thường đại diện cho **workload/service principal**. Đặc biệt:

~~~text
Authorization Code / delegated access:
    subject = Alice
    client = expense-viewer
    policy = quyền Alice có thể ủy quyền trong ngữ cảnh

Client Credentials:
    principal = expense-sync-service
    user consent = không có End-User trong luồng
    policy = quyền workload và quản trị application permissions
~~~

Không để Expense Sync Service có scope rộng tự xử lý yêu cầu của Alice bằng quyền service mạnh hơn mà không kiểm tra quyền Alice. Đây là một dạng **confused deputy**.

### 7.4. Consent screen phải thể hiện đúng publisher

Nếu một client được phép tự đặt display name “Finance Security Team”, user có thể bị lừa tưởng ứng dụng nội bộ đáng tin. AS nên quản lý verified publisher/client display name, logo và policy đăng ký; cảnh báo ứng dụng chưa được xác minh khi phù hợp.

Màn hình consent **không nên dùng tên scope kỹ thuật khó hiểu làm mô tả duy nhất**, nhưng cũng không được rút gọn đến mức che quyền nhạy cảm. Ví dụ `expenses:approve` phải được diễn giải rõ là quyền **phê duyệt chi phí** nếu grant có thể bao gồm quyền đó.

## 8. Consent trong OAuth/OIDC không nhất thiết là một popup cho mỗi lần login

Một hệ thống có thể có **remembered consent**, consent do quản trị viên cấp trong phạm vi thẩm quyền, hoặc cơ chế xác lập authorization bằng cách khác đã được policy cho phép. **RFC 6749 không yêu cầu AS phải hiển thị một hộp thoại consent riêng trong mọi authorization request**.

Điểm quan trọng: **không hiển thị màn hình** không có nghĩa **không kiểm tra policy**.

### 8.1. Quyết định consent và authorization policy độc lập

| Tình huống | Có thể không hiển thị consent? | Policy bắt buộc |
|---|---|---|
| Client first-party được tin cậy theo chính sách AS | Có thể, theo chính sách sản phẩm | Client/subject/scope/resource/tenant vẫn được kiểm |
| User đã chấp thuận grant tương ứng, còn hợp lệ | Có thể dùng remembered consent | Không vượt scopes/resources đã chấp thuận; xét thay đổi quyền |
| Client xin thêm scope nhạy cảm mới | Thường cần consent/approval mới khi policy yêu cầu | Scope mới vẫn phải hợp lệ với client/user |
| User chuyển tenant hoặc tài khoản | Không thể dùng bừa consent từ ngữ cảnh cũ | Binding của grant với subject/tenant phải đúng |
| Ứng dụng không được phép gọi API này | Không | Policy phải từ chối dù UX có hiển thị consent |
| Server-to-server qua client credentials | Không có tương tác End-User | Workload/client authorization riêng |

Một user có thể đã consent `expenses:read` hôm qua nhưng hôm nay bị chuyển khỏi phòng ban A. Token mới không được cấp quyền dựa trên một **bản consent cũ** mà bỏ qua policy hiện tại.

### 8.2. `prompt=consent` trong OIDC không phải lệnh tăng quyền

OIDC hỗ trợ các giá trị `prompt` theo profile, trong đó `prompt=consent` yêu cầu OP hiển thị tương tác consent. Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code&client_id=expense-viewer&scope=openid%20expenses%3Aread&prompt=consent&state=<STATE>&redirect_uri=<REGISTERED_URI>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Client gửi `prompt=consent` **không buộc AS** cấp scope mà client không được phép. Nó là tham số yêu cầu hành vi tương tác của OP trong OIDC; quy tắc authentication/authorization và client registration vẫn phải được thực thi.

Tương tự, `prompt=none` yêu cầu xử lý không tương tác theo profile, **không phải** lệnh bỏ qua consent hoặc đăng nhập cần thiết. Nếu không thể đáp ứng mà không tương tác, OP phải trả lỗi OIDC thích hợp (ví dụ `consent_required` trong trường hợp cần consent).

### 8.3. `openid`, profile/email và claims là yêu cầu thông tin

Với OIDC:

~~~text
scope=openid profile email
~~~

Client đang yêu cầu chức năng xác thực OIDC và các thông tin profile/email theo hợp đồng OP. Điều này **không** có nghĩa được đọc mọi trường hồ sơ, xem mọi tài khoản liên quan hoặc gọi API nghiệp vụ ngoài audience.

Nếu UserInfo endpoint được sử dụng, client phải so khớp **`sub` của UserInfo với `sub` của ID token đã xác minh** trước khi dùng các claims khác. Một UI consent cho phép chia sẻ email không biến UserInfo response thành nguồn roles của Expense API.

### 8.4. Chỉ cho consent nội dung đã được giải thích rõ

Consent UI phải tránh:

- Hiển thị một nút “Đồng ý” nhưng không nói **ứng dụng nào** và **dữ liệu/quyền nào**.
- Gộp quyền đọc với quyền xóa thành thông điệp “cải thiện trải nghiệm”.
- Giấu việc app có thể dùng refresh token để truy cập sau khi user rời trình duyệt.
- Mập mờ giữa quyền của user và quyền tổ chức.
- Đưa URL lạ hoặc logo không được kiểm chứng làm dấu hiệu tin cậy.

Trường hợp có **offline access** hoặc refresh token, UX và policy nên giải thích phù hợp khi ứng dụng có thể tiếp tục truy cập không cần user tương tác lại, trong giới hạn grant.

## 9. Consent theo thời gian: grant có thể còn, quyền nghiệp vụ đã thay

Quyền của user, trạng thái tổ chức, role, bản ghi, đồng ý của người dùng và thời hạn token có thể **thay đổi ở các thời điểm khác nhau**.

~~~text
T0: Alice là FINANCE_APPROVER, chấp thuận Expense Viewer.
T1: AS cấp access token expires_in=900.
T2: Alice bị gỡ role FINANCE_APPROVER.
T3: Expense Viewer dùng access token còn hạn để POST /approve.
~~~

**Kết quả an toàn:** nếu chính sách yêu cầu áp quyền hiện tại, Expense API phải từ chối ở T3 dù token chưa hết hạn và consent tại T0 còn được lưu.

### 9.1. Những loại trạng thái độc lập

| Trạng thái | Ví dụ | Thay đổi có tác động gì? |
|---|---|---|
| **Consent record** | Alice chấp thuận Expense Viewer đọc dữ liệu | Có thể rút lại; ảnh hưởng grant/cấp token tùy triển khai |
| **Authorization grant** | AS liên kết subject + client + scope + resource | Có thể bị thu hồi, giới hạn hoặc hết hạn |
| **Access token** | JWT/opaque có TTL nhất định | Có thể còn hiệu lực dù consent đã rút nếu không có cơ chế chặn |
| **Refresh token** | Quyền xin access token mới tại AS | Rotation, revocation và reuse detection |
| **Business role** | Alice còn quyền phê duyệt? | Có thể đổi độc lập với consent |
| **Resource ACL/owner** | Khoản chi thuộc phòng ban nào? | Có thể đổi sau token issuance |
| **Tenant membership** | Alice còn thuộc tenant A? | Có thể bị gỡ tức thì |

**Một record “consent approved” không thể thay thế cả bảng role, ACL, tenant membership và trạng thái grant.**

### 9.2. Rút lại consent và thu hồi token

Khi Alice rút lại quyền đã chấp thuận cho một client, hệ thống cần xác định phạm vi tác động:

1. **Consent store:** đánh dấu quyền chấp thuận tương ứng không còn dùng được cho lần ủy quyền tiếp theo.
2. **AS grant state:** thu hồi hoặc cập nhật grant theo chính sách; chặn refresh khi thích hợp.
3. **Refresh tokens:** sử dụng cơ chế revocation/rotation và bảo vệ family khi cần.
4. **Access tokens:** xác định RS có introspection, denylist, session version hoặc chỉ JWT offline đến `exp`.
5. **Resource server:** tiếp tục áp business policy/ACL ở mọi request.
6. **UI/user communication:** mô tả việc thu hồi có hiệu lực như thế nào và liệu token đã phát hành còn một khoảng sống hay không.

Không được quảng bá “rút consent là mọi access token mất hiệu lực ngay lập tức” nếu kiến trúc dùng JWT offline và không có cơ chế thu hồi trước expiry.

### 9.3. JWT offline và thời điểm kiểm tra policy

JWT access token có thể được xác minh mà không gọi AS mỗi lần. Điều đó giúp hiệu năng nhưng có chi phí: role/ACL nằm trong JWT có thể **cũ**.

Giảm rủi ro bằng:

- **TTL** access token phù hợp mức nhạy cảm.
- Đặt **quyền động** như ownership, tenant membership và approval limit ở nơi có thể kiểm tra hiện thời.
- Khi cần gần thời gian thực, dùng introspection/state check/denylist hoặc policy cache có TTL ngắn.
- Có chiến lược invalidation cho thay đổi quyền khẩn cấp.
- Không coi một claim `roles` còn chữ ký là bản sao vĩnh viễn của policy.

Các yêu cầu về tính tức thời cần được xác định trong SLO/security design; không có một cấu hình phù hợp mọi ứng dụng.

### 9.4. Refresh token không phải cơ hội tăng scope

Giả sử grant ban đầu:

~~~text
Client: expense-viewer
Subject: alice-123
Scope: expenses:read
Resource: https://expenses.example.com
~~~

Khi refresh:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&scope=expenses%3Aread%20expenses%3Aapprove&client_id=expense-viewer
~~~

AS **không được** mở rộng scope vượt grant ban đầu chỉ vì refresh token hợp lệ. Theo RFC 6749, scope trong refresh request không được vượt phạm vi đã cấp; AS còn cần áp chính sách về client, subject và trạng thái grant.

Với public client được cấp refresh token, OAuth 2.0 Security BCP (RFC 9700) yêu cầu **refresh token rotation hoặc sender constraint** phù hợp để phát hiện/giảm nguy cơ token bị đánh cắp sử dụng lại. Consent không thay cơ chế replay protection.

### 9.5. Lịch sử consent không thay đổi business ownership

Nếu Alice đã từng cho app đọc đơn hàng `order-721`, rồi sau đó bản ghi được chuyển sang tenant khác hoặc quyền chia sẻ bị thu hồi, việc có lịch sử consent không làm record vẫn thuộc quyền Alice.

Resource Server phải xác định theo **dữ liệu/tình trạng hiện tại** hoặc theo mô hình nhất quán được thiết kế, thay vì lấy một bản consent trước đây làm nguồn quyết định access.

## 10. Consent phishing và confused deputy

Màn hình consent có thể trở thành **điểm tấn công xã hội**. Kẻ tấn công không cần hack token endpoint nếu có thể lừa người dùng chấp thuận một ứng dụng hoặc quyền nguy hiểm.

### 10.1. Consent phishing

Ví dụ:

~~~text
Thông báo giả:
    "Vui lòng cấp quyền để hoàn tất xác minh tài khoản."

Client được mô tả:
    "Expense Security Validator"

Scope thực tế:
    expenses:read
    expenses:export
    offline_access
~~~

User có thể vào đúng domain của AS và vẫn bị dụ phê duyệt một client do attacker đăng ký. **Domain OP/AS hợp lệ không chứng minh ứng dụng/publisher là đáng tin**.

Các lớp phòng vệ:

- AS kiểm soát **client registration, verified publisher, redirect URI** và loại scopes được xin.
- Consent UI hiển thị rõ client, nhà phát triển, scope và hậu quả của offline access khi liên quan.
- Chính sách chặn/hạn chế ứng dụng chưa được xác minh hoặc scope nguy hiểm.
- Admin approval khi policy yêu cầu, với verification rằng admin có thẩm quyền.
- Giám sát grant bất thường, các scopes nhạy cảm và số lượng users chấp thuận một client mới.
- Người dùng có thể xem, thu hồi các kết nối đã cấp.

Consent UI **không phải biện pháp bảo vệ duy nhất**. AS và RS cần policy bất kể người dùng bị dụ nhấn vào đâu.

### 10.2. Confused deputy khi backend dùng service token

Giả sử Expense Viewer chỉ có quyền đọc chi phí của Alice, nhưng backend Expense Export Service có service token `expenses:read-all`. Backend không được đọc mọi record theo yêu cầu `expenseId` của Alice mà bỏ kiểm tra quyền Alice.

~~~text
Alice ----> Expense Viewer ----> Expense Export Service
               (scope read)           (service token read-all)

Sai:
    Service tin caller nội bộ và trả mọi record.

Đúng:
    Service kiểm tra actor/user, tenant, resource và delegated scope;
    hoặc dùng token exchange/on-behalf-of đúng policy.
~~~

Đây là lỗi **confused deputy**: một thành phần có quyền mạnh hơn được dùng để thực hiện yêu cầu ngoài quyền người dùng. Consent ở frontend không sửa được lỗi đó.

### 10.3. Consent không thay chống CSRF, PKCE hoặc redirect validation

Trong Authorization Code flow:

- **PKCE S256** ràng buộc code với verifier của request gốc, giúp phòng code interception/injection.
- **State/request binding** chống lẫn response/login CSRF theo thiết kế.
- **Issuer binding** phòng authorization server mix-up.
- **Redirect URI registration** ngăn chuyển code tới attacker.
- **Client authentication** bảo vệ confidential client khi token exchange.
- **Consent** xử lý chấp thuận một yêu cầu trong phạm vi hợp lệ.

Không loại bỏ các kiểm tra mật mã/giao thức vì “người dùng đã thấy và bấm nút Đồng ý”. Chúng bảo vệ các vấn đề khác nhau.

## 11. Thiết kế Authorization Server: không cấp scope chỉ dựa trên consent record

Ở AS, một request cấp token phải vượt qua **client validation, grant policy và consent policy**. Dưới đây là cách tách trách nhiệm, không phải một thuật toán chuẩn cho mọi loại grant.

### 11.1. Authorization request có nhiều nguồn dữ liệu

~~~text
Request do client gửi:
    client_id = expense-viewer
    scope = expenses:read expenses:approve
    resource = https://expenses.example.com

Registration đáng tin ở AS:
    allowedGrantTypes = authorization_code
    allowedScopes = expenses:read
    allowedResources = https://expenses.example.com

Subject/session được xác minh:
    sub = alice-123
    tenant = A
    delegatableActions = expenses:read

Consent:
    Alice chỉ chấp thuận expenses:read

Grant hợp lệ:
    client = expense-viewer
    sub = alice-123
    scope = expenses:read
    audience = https://expenses.example.com
~~~

Nếu client xin `expenses:approve` nhưng registration không cho phép, AS có thể **từ chối toàn bộ request** hoặc áp policy giới hạn scope theo giao thức/UX, nhưng không được cấp scope ngoài policy. Tất cả giá trị trong **request do client gửi** là dữ liệu cần kiểm chứng, không phải quyền mặc nhiên.

### 11.2. Pseudocode sai: click đồng ý là cấp mọi scope

~~~java
// SAI: scope do client xin được cấp thẳng nếu user nhấn Đồng ý.
TokenResponse approve(ConsentForm form) {
    if (form.isApproved()) {
        return tokenIssuer.issue(
            form.clientId(),
            form.subject(),
            form.requestedScopes());
    }
    throw new AccessDeniedException("User denied");
}
~~~

Sai ở nhiều chỗ:

- `clientId`, `subject`, `requestedScopes` lấy từ form chưa chứng minh nguồn tin.
- Không kiểm registration, grant type, redirect URI, issuer, tenant, resource.
- Không kiểm user có thể ủy quyền scope đó không.
- Không ràng buộc consent với **authorization request gốc và user session**.
- Không kiểm bản consent còn hiệu lực, đã bị hủy hoặc bị dùng nhầm cho client khác.
- Không có quy tắc token issuance/expiry/refresh phù hợp.

### 11.3. Pseudocode đúng hướng: tạo grant sau khi kiểm policy

~~~java
// Pseudocode: mọi type và helper là thành phần minh họa,
// KHÔNG phải API Spring Authorization Server có sẵn.
ApprovedGrant evaluateAuthorizationRequest(
        VerifiedUser user,
        RegisteredOAuthClient client,
        VerifiedAuthorizationRequest request,
        ConsentDecision decision) {

    require(client.allowedGrant("authorization_code"));
    require(client.registeredRedirectUri(request.redirectUri()));
    require(request.issuer().equals(client.trustedIssuer()));
    pkcePolicy.verifyS256RequiredForClient(client, request);

    // Chỉ quyền client được phép xin và tài nguyên AS được phép cấp.
    Set<String> eligibleScopes = clientPolicy.intersectAllowedScopes(
        client, request.requestedScopes());

    Set<String> eligibleResources = resourcePolicy.intersectAllowed(
        client, request.requestedResources());

    // Áp business/delegation policy khi có nghĩa trong grant này.
    Set<String> delegatableScopes = delegationPolicy.filter(
        user, client, eligibleScopes, eligibleResources);

    ConsentResult consent = consentPolicy.evaluateFor(
        user, client, request, decision, delegatableScopes);

    require(consent.isApprovedOrValidExistingConsent());

    Set<String> granted = policyFinalizer.finalizeGrantedScopes(
        delegatableScopes, consent.consentedScopes());

    require(granted != null);
    return grantStore.createBoundGrant(
        user.verifiedSubject(),
        client.id(),
        granted,
        eligibleResources,
        request.authorizationRequestId());
}
~~~

Điểm chính:

- `VerifiedUser` được xác thực bằng AS, không lấy từ input `sub` tùy ý.
- `RegisteredOAuthClient` phải đến từ kho client registration đáng tin.
- `VerifiedAuthorizationRequest` phải được liên kết đúng state/PKCE/issuer/redirect.
- Kết quả consent không được làm **rộng** `eligibleScopes` hoặc vượt policy.
- AS có thể từ chối request khi một scope không hợp lệ, thay vì luôn downscope âm thầm.
- `ApprovedGrant` cần có TTL, issuer, client binding, subject, resource/audience và grant state.

**Không sử dụng pseudocode trên làm production Authorization Server.** Việc mã hóa grant, OAuth error responses, client authentication, code single-use, PKCE, consent transaction và token issuance cần framework được kiểm thử.

### 11.4. Chính sách tại token endpoint phải ràng buộc với grant

Khi client đổi authorization code tại token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<CODE>&redirect_uri=<REGISTERED_URI>&client_id=expense-viewer&code_verifier=<VERIFIER>
~~~

AS phải kiểm tra code thuộc đúng client/redirect, còn hạn, chưa dùng, PKCE verifier đúng, client authentication khi áp dụng, và chỉ cấp token **trong giới hạn grant đã phê duyệt**.

Một request token endpoint không được tự khai `scope=expenses:approve` hoặc `sub=admin` rồi mở rộng quyền từ một authorization code chỉ cho phép `expenses:read`.

### 11.5. Policy có thể thay đổi giữa authorization và token exchange

Tình huống:

~~~text
T0: Alice bắt đầu authorization request.
T1: AS hiện màn hình consent.
T2: Quản trị viên gỡ role của Alice.
T3: Alice nhấn Đồng ý.
T4: Client đổi authorization code.
~~~

Với grant nhạy cảm, AS nên xác định rõ **thời điểm kiểm tra role/policy và cơ chế recheck** trước token issuance. Không nên giả định role còn hiệu lực chỉ vì request được tạo ở T0. Nếu policy đổi, có thể cần từ chối, downscope hoặc yêu cầu authorization mới.

Không có một chiến lược recheck duy nhất cho mọi nguồn dữ liệu; lựa chọn phải đáp ứng threat model, độ tươi quyền và consistency của hệ thống.

## 12. Spring Security Resource Server: enforce quyền sau consent

Một API Java/Spring có thể sử dụng Spring Security OAuth2 Resource Server để kiểm tra access token. Đây chỉ là **authentication/token validation layer**; cần thêm business authorization.

### 12.1. Cấu hình kiểm JWT access token

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Đây là ví dụ khởi điểm. Resource Server còn cần **expected audience validator** dành cho Expense API, kiểm tra token type/profile theo hợp đồng, thời gian, scope mapping và chính sách thu hồi khi áp dụng. Nếu AS cấp **opaque access token**, cần introspection hoặc cơ chế xác minh phù hợp thay JWT validation.

Không coi cấu hình `issuer-uri` đơn lẻ bảo đảm mọi ràng buộc audience/nghiệp vụ đã được thực thi đúng.

### 12.2. SecurityFilterChain để xác thực request

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ExpenseApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Đây không phải production config đầy đủ.** Cần session/CSRF tùy API, token validators, CORS, error response, security headers, method security, audit và token audience theo phiên bản Spring đang dùng.

### 12.3. Endpoint check scope rồi gọi service kiểm object

~~~java
// Pseudocode Spring MVC minh họa; cần bật method security
// và cấu hình scope-to-authority converter phù hợp.
@PreAuthorize("hasAuthority('SCOPE_expenses:read')")
@GetMapping("/api/expenses/{id}")
public ExpenseDto getExpense(
        @PathVariable long id,
        Authentication authentication) {

    VerifiedActor actor = actorFactory.fromValidatedAuthentication(
        authentication);
    return expenseService.readForActor(actor, id);
}
~~~

Các type `VerifiedActor`, `actorFactory` và `expenseService.readForActor` là **thành phần do ứng dụng định nghĩa**, không phải API Spring có sẵn.

Service phải kiểm tra tenant, owner, ACL và trạng thái record ở chính thao tác truy vấn hoặc trong một authorization layer đáng tin:

~~~java
public ExpenseDto readForActor(VerifiedActor actor, long expenseId) {
    Expense expense = repository.findForAuthorizedViewer(
        expenseId,
        actor.tenantId(),
        actor.localUserId());

    if (expense == null) {
        // Có thể trả 404 để không tiết lộ resource tồn tại.
        throw new ResourceNotFoundException();
    }
    return ExpenseDto.from(expense);
}
~~~

Đây là pseudocode service: có thể cần ACL shares, organizational membership, data sensitivity và các policy khác. **Không** lấy `actor.localUserId()` từ một HTTP header chưa được xác minh hoặc từ `sub` có định dạng tự khai. Mapping subject và tenant phải được giải quyết an toàn theo token/session đã xác minh.

### 12.4. Duyệt khoản chi: scope và role vẫn chưa đủ

~~~java
// Pseudocode: diễn đạt business policy; không tự cung cấp
// concurrency control hay full transaction boundaries.
public void approveExpense(VerifiedActor actor, long expenseId) {
    authorizationService.requireActionScope(
        actor, "expenses:approve");

    transaction.run(() -> {
        Expense expense = repository.lockAndRead(expenseId);

        businessPolicy.requireApproverRole(actor, expense.tenantId());
        businessPolicy.requireSameTenant(actor, expense);
        businessPolicy.requireWithinApprovalLimit(actor, expense.amount());
        businessPolicy.requireNotOwnExpense(actor, expense.ownerId());
        businessPolicy.requireStatus(expense, "SUBMITTED");

        expense.approve(actor.localUserId());
        repository.save(expense);
    });
}
~~~

**Consent không xuất hiện trong business policy như một nút cho phép tuyệt đối.** Grant/scope là điều kiện đi qua security boundary; quyết định cuối cùng phải dựa trên principal, action và resource. Một approver cũng có thể bị từ chối vì vượt hạn mức hoặc không được duyệt khoản chi của chính mình.

### 12.5. Chống TOCTOU và stale authorization

Nếu API kiểm quyền trước rồi record bị chuyển tenant/đổi owner trước khi update, có thể xảy ra lỗi **time-of-check to time-of-use**:

~~~text
T0: Check record thuộc tenant A -> ALLOW
T1: Record chuyển sang tenant B
T2: Update record không tái kiểm -> hành động ngoài quyền
~~~

Với thao tác nhạy cảm, cân nhắc **transaction + locking/versioning + kiểm business policy tại thời điểm update**. Không giải quyết bằng consent hay scope rộng hơn.

## 13. Tầng policy thống nhất cho nhiều API và công việc nền

Một hệ thống có thể có:

~~~text
Browser / Mobile / Partner Client
           |
           v
     API Gateway
           |
     Expense Service ------> Report Worker
           |                     |
     Expense Database        Data Warehouse
~~~

Nếu chỉ đặt check ở gateway:

- Report Worker có thể đọc dữ liệu vượt tenant khi nhận job từ Expense Service.
- Một batch export có thể bỏ qua policy áp trên endpoint `GET /expenses/{id}`.
- Thao tác nội bộ trực tiếp giữa các service có thể bypass nơi chặn ban đầu.

**Defense in depth:** gateway có thể kiểm token và rate limit, nhưng mỗi service có quyền đọc/ghi dữ liệu nhạy cảm phải thực thi policy tương ứng tại **trust boundary của nó**.

### 13.1. Policy Decision Point và Policy Enforcement Point

Trong kiến trúc phức tạp, có thể phân chia:

| Thành phần | Vai trò |
|---|---|
| **Policy Enforcement Point (PEP)** | Chặn request/thao tác nếu policy không cho phép |
| **Policy Decision Point (PDP)** | Tính quyết định ALLOW/DENY dựa trên subject/action/resource/context |
| **Policy Information Point (PIP)** | Cung cấp dữ liệu như tenant membership, roles, ownership |
| **Authorization Server** | Cấp token/grant đã được policy ràng buộc, không thay toàn bộ authorization ở RS |

Thiết kế authorization có thể dùng RBAC, ABAC, ACL hoặc kết hợp. Điều cốt yếu là **policy phải có nguồn dữ liệu tin cậy và được thực thi nhất quán**, không phải “có consent record nên mặc định allow”.

### 13.2. Default deny khi không đủ ngữ cảnh

Ví dụ:

~~~text
Token valid: YES
Scope read: YES
Actor identity: YES
Tenant của resource: UNKNOWN

Decision: DENY (hoặc lỗi có kiểm soát), không tự ALLOW.
~~~

Nếu policy service hoặc membership database không truy cập được, một số hệ thống phải **fail closed** đối với hành động nhạy cảm. Trường hợp phục vụ dữ liệu cache read-only có thể có policy availability riêng, nhưng cần được phê duyệt có ràng buộc, không ngầm default allow khi kiểm quyền thất bại.

### 13.3. Tránh tin identity headers do client tự đặt

Một backend có thể nhận:

~~~http
X-User-Id: alice-123
X-Tenant-Id: finance
X-Role: ADMIN
~~~

Không tin các header này chỉ vì API nằm sau gateway. Nếu gateway chuyển identity context nội bộ, phải xóa giá trị từ untrusted caller, bảo vệ nguồn và tính toàn vẹn (mTLS/signing/network boundary theo thiết kế) và ngăn bypass gateway. **Consent không chứng minh authenticity của request headers**.

### 13.4. Mỗi request cần actor context phù hợp

Với một background job chạy sau nhiều giờ:

- Job được tạo bởi ai và đã được phép chạy tại thời điểm tạo?
- Nếu quyền user bị thu hồi, job tiếp tục có được phép không?
- Job mang token user, token exchanged có delegation, hay service credential riêng?
- Output có chứa dữ liệu tenant khác không?
- Quyền export có khác quyền read từng bản ghi không?

Một consent cho ứng dụng lúc tạo job **không tự giải quyết** việc tác vụ nền chạy sau khi user rời tổ chức hoặc các điều kiện nghiệp vụ đã thay đổi. Cần workflow policy riêng.

## 14. Threat model: khi consent bị dùng như lối tắt authorization

| Mối đe dọa/lỗi | Biểu hiện | Phòng vệ chính |
|---|---|---|
| **Scope escalation** | AS cấp mọi scope user nhấn “Đồng ý” dù client không được phép | Client registration và grant policy ở AS |
| **Audience confusion** | Access token cho Expense API được chấp nhận ở Billing API | Kiểm `aud` và token profile tại từng RS |
| **BOLA/IDOR** | Có scope read thì lấy bất kỳ record ID | Object-level, tenant/ownership/ACL check |
| **Cross-tenant access** | Consent tenant A được áp cho tài nguyên tenant B | Tenant binding/membership và policy theo resource |
| **Privilege escalation** | Một user tự duyệt role admin qua consent | Role/permission do admin/policy kiểm soát |
| **Admin consent abuse** | Admin tenant A cấp quyền cho tenant B | Tenant-scoped admin authority validation |
| **Consent phishing** | User đồng ý cho client do attacker kiểm soát | Verified client, publisher, scope restrictions, UX |
| **Overbroad token grant** | AS phát token `read-all` khi chỉ được `read-own` | Scope/grant policy và resource constraint |
| **Stale authorization** | JWT còn role sau khi bị gỡ quyền | TTL/state checks và policy hiện thời ở RS |
| **Refresh scope escalation** | Refresh xin scope mới không thuộc grant | Không vượt original grant, reauthorization khi cần |
| **Revocation gap** | UI báo “đã thu hồi” nhưng JWT offline vẫn hoạt động | Thiết kế revoke/denylist/introspection/TTL minh bạch |
| **Confused deputy** | Service token mạnh được dùng phục vụ user yếu quyền | Delegation/actor context, downstream authorization |
| **Consent replay/confusion** | Kết quả chấp thuận từ request A dùng cho request B | Consent transaction binding và CSRF/state protection |
| **Malicious identity header** | Caller tự khai role/admin/tenant | Kiểm principal từ credential và trusted context |
| **Token substitution** | Dùng ID token làm access token hoặc refresh token gọi API | Token type/profile validation |
| **Insecure batch/export** | Endpoint list lọc tenant nhưng export không lọc | Áp policy ở data access layer cho mọi đường truy cập |
| **Untrusted client display name** | Client attacker giả là ứng dụng chính thức | Publisher verification, registration review |
| **Privacy overreach** | OAuth approval bị coi là đồng ý xử lý mọi mục đích | Privacy policy và mục đích sử dụng riêng |

### 14.1. Hai kiểu “đồng ý” không đủ bảo vệ

**Kiểu thứ nhất: đồng ý cho client truy cập dữ liệu của mình.**

Người dùng có thể muốn cấp quyền, nhưng không biết client đang yêu cầu quá rộng; AS phải áp policy. Nếu client hợp lệ được cấp scope `expenses:read`, API vẫn lọc đối tượng.

**Kiểu thứ hai: admin đã duyệt ứng dụng.**

Admin có thể có thẩm quyền phê duyệt client ở tenant A, nhưng không vì thế mọi user và tài nguyên trong tenant A đều tự có quyền `read-all`, `delete-all` hay `export-all`. Cần thiết kế chính xác application permissions, user delegation, tenant boundaries và downstream policy.

### 14.2. Bảng quyết định giao thoa các lớp

| Consent cần thiết/đã có? | Client được phép? | Token/grant hợp lệ? | Resource policy cho phép? | Kết quả |
|---|---|---|---|---|
| Không | Có | Chưa cấp | Có thể | Không cấp grant nếu policy yêu cầu consent |
| Có | **Không** | Không được cấp hợp lệ | Bất kỳ | **DENY** |
| Có | Có | **Không** | Bất kỳ | **DENY** |
| Có | Có | Có | **Không** | **DENY** ở RS |
| Có | Có | Có | Có | Có thể **ALLOW** nếu tất cả điều kiện khác đạt |
| Không áp dụng consent ở grant này | Có | Có | Có | Có thể **ALLOW** theo policy tương ứng |

**Bảng là mô hình khái niệm**, không chỉ định một HTTP status cho mọi tình huống. Authentication và authorization failures nên có error semantics phù hợp với endpoint đang xử lý.

## 15. Lỗi OAuth và HTTP: đặt lỗi ở đúng ranh giới

### 15.1. Consent bị từ chối tại authorization endpoint

Nếu user từ chối yêu cầu trong Authorization Code flow, AS có thể trả lỗi:

~~~http
HTTP/1.1 302 Found
Location: https://expense-viewer.example.com/callback?error=access_denied&state=<ORIGINAL_STATE>
~~~

Đó là **authorization response error** theo OAuth, không phải access token hay bằng chứng user không tồn tại. AS cần kiểm tra redirect URI trước khi chuyển lỗi. Khi URI không hợp lệ, không redirect thông tin về nơi không đáng tin.

Client cần kiểm tra state/issuer/ngữ cảnh callback và hiển thị thông báo phù hợp, không tự retry bằng một scope rộng hơn hoặc bỏ PKCE.

### 15.2. Client xin scope không hợp lệ

Khi AS nhận scope không tồn tại hoặc không hợp lệ:

- Ở authorization endpoint có thể trả `invalid_scope` theo quy tắc OAuth nếu request và redirect đủ điều kiện trả lỗi.
- Ở token endpoint cũng có lỗi `invalid_scope` cho ngữ cảnh tương ứng.
- Với client không được dùng một grant type, có thể là `unauthorized_client`.
- Nếu client authentication thất bại tại token endpoint, xử lý `invalid_client` đúng contract.

Không nên dùng `access_denied` cho mọi lỗi policy rồi mất khả năng phân biệt user từ chối với client không có quyền; đồng thời **không tiết lộ metadata nhạy cảm của user/tenant** trong error descriptions.

### 15.3. Resource server nhận token thiếu hoặc sai

Khi gọi API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="expenses", error="invalid_token"
~~~

Đây là một response thường dùng khi access token được trình nhưng không hợp lệ, chẳng hạn sai issuer/audience hoặc hết hạn theo contract.

Với token hợp lệ nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="expenses", error="insufficient_scope", scope="expenses:approve"
~~~

Với scope đủ nhưng Alice không có quyền trên record 748:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "error": "access_denied"
}
~~~

API cũng có thể dùng **404** nếu policy cần che sự tồn tại của object. Body trên là **contract ứng dụng minh họa**, không phải định dạng lỗi bắt buộc của RFC 6750. Không đưa thông tin tenant khác hoặc chi tiết bản ghi bị từ chối vào response.

### 15.4. Phân biệt 401 và 403

| Vấn đề | Kết quả thường phù hợp |
|---|---|
| Không có access token ở endpoint yêu cầu bearer | 401 và challenge |
| Token sai chữ ký, issuer/audience, hết hạn, opaque inactive | 401 với `invalid_token` khi phù hợp |
| Credential sai cú pháp | OAuth bearer `invalid_request`/HTTP tương ứng theo profile |
| Token hợp lệ nhưng scope thiếu | 403 với `insufficient_scope` khi phù hợp |
| Token đủ scope nhưng record ngoài tenant/ACL | 403 hoặc 404 theo policy |
| User từ chối OAuth consent trên browser | OAuth authorization error `access_denied` |
| Client bị chặn xin scope tại AS | OAuth error phù hợp ở AS, không phát token vượt policy |

**Không dùng lỗi 401/403 như tín hiệu cho client “thử xin quyền admin rồi xem”.** Việc xin thêm quyền phải là một authorization request được phép theo chính sách, có UX và approval phù hợp.

## 16. Ma trận kiểm thử: consent không thể vượt policy

Một hệ thống có thể có màn hình consent đẹp và flow PKCE đúng nhưng **authorization logic vẫn sai**. Bộ test cần tách AS, consent UI, token issuance và RS.

### 16.1. Authorization Server và consent

| Kịch bản | Kỳ vọng |
|---|---|
| Client đăng ký `expenses:read`, xin `expenses:approve` | Không cấp scope approve ngoài registration |
| User chỉ có read, đồng ý request approve | Không cấp quyền approve nếu policy không cho phép |
| Consent screen ghi read nhưng token được cấp write | Test fail; scope phải khớp grant/policy/UX |
| Client xin audience ngoài allowed resources | Không cấp token cho resource trái policy |
| Client cố tự khai subject khác qua query | Không thay subject đã xác thực |
| Client xin cross-tenant access ngoài quyền | Từ chối hoặc giới hạn theo policy |
| User từ chối consent | Không cấp grant tương ứng; trả OAuth error thích hợp |
| User đã consent read, client xin thêm delete | Không tự dùng consent cũ để cấp quyền mới |
| User chuyển account giữa lúc consent | Không dùng subject/session cũ cho account mới |
| Người không có admin role nhấn “admin approve” | Không có hiệu lực cấp quyền quản trị |
| Admin của tenant A phê duyệt cho tenant B | Từ chối nếu không có thẩm quyền ở B |
| Consent bị rút trước khi phát token | Áp policy trạng thái grant/consent mới |
| Role bị gỡ trong lúc user đang xem consent | AS xử lý theo policy recheck, không cấp quyền đã mất |
| Confidential client đổi code không xác thực | Không cấp token |
| PKCE verifier sai nhưng consent đã được approve | Không cấp token |
| Authorization response sai issuer/state | Client từ chối trước token exchange |

### 16.2. Token claims và token lifecycle

| Kịch bản | Kỳ vọng |
|---|---|
| JWT ký hợp lệ nhưng issuer không tin cậy | RS từ chối |
| JWT ký hợp lệ nhưng audience dành cho API khác | RS từ chối |
| JWT hết hạn/opaque inactive | RS từ chối |
| ID token gửi thay access token | RS từ chối token sai mục đích |
| Token có scope `expenses:read`, client yêu cầu `expenses:approve` | RS từ chối approve |
| Token có role admin quá cũ sau khi user bị thu hồi role | Thiết kế TTL/recheck bảo đảm policy hiện thời theo yêu cầu |
| Refresh token xin scope rộng hơn grant | AS từ chối tăng scope |
| Refresh token bị reuse sau rotation | AS xử lý replay/grant family theo policy |
| Consent revoked nhưng JWT offline còn hạn | Test xác nhận hành vi revoke/TTL đã công bố, không giả định vô hiệu ngay |
| Đổi resource/audience ở token exchange | Không vượt policy/grant ban đầu |
| Mất client secret hoặc token bị log | Quy trình redaction/revocation/incident response hoạt động |
| Admin thu hồi application registration | AS/RS ngăn token mới và xử lý token hiện hữu theo thiết kế |

### 16.3. Resource authorization theo object và tenant

| Kịch bản | Kỳ vọng |
|---|---|
| Alice có `expenses:read`, đọc record của mình | ALLOW nếu policy khác đạt |
| Alice có `expenses:read`, đọc record của Bob | DENY nếu không có sharing/ủy quyền |
| Alice có read, đổi path sang record tenant B | DENY |
| Alice có approve scope nhưng không có approver role | DENY |
| Alice là approver, duyệt khoản chi của chính mình | DENY nếu separation-of-duties policy cấm |
| Alice là approver, duyệt khoản vượt hạn mức | DENY |
| Alice có quyền sửa nhưng record đã LOCKED | DENY |
| Alice không thuộc tenant trong request | DENY ngay cả khi token có tenant claim không còn đúng |
| Endpoint list có lọc tenant nhưng export bỏ lọc | Test fail |
| Background job chạy bằng service token, lấy dữ liệu tenant khác | DENY nếu ngoài delegation/policy |
| API Gateway đã kiểm token nhưng service downstream bỏ kiểm object | Test fail |
| Resource chuyển owner giữa check và update | Transaction/locking/versioning ngăn TOCTOU |
| Policy service không sẵn sàng khi duyệt chi phí | Fail closed theo risk policy; không mặc định allow |

### 16.4. User experience, consent records và phishing

| Kịch bản | Kỳ vọng |
|---|---|
| Consent hiển thị tên client không được xác minh | Không cho mạo danh publisher/first-party client |
| Client xin `expenses:approve` nhưng UX chỉ nói “xem” | Test UX/security fail |
| User không bấm đồng ý, app vẫn nhận delegated grant cần consent | Test fail |
| User bấm từ chối | Không có automatic retry chuyển sang scope khác ngoài ý định |
| App dùng remembered consent từ tenant A ở tenant B | Từ chối context không khớp |
| User bấm revoke app | Quy trình grant/token state và UI mô tả đúng hiệu lực |
| Request đăng nhập OIDC `prompt=none` nhưng cần consent | Trả lỗi giao thức thích hợp, không tự bỏ consent |
| Request `prompt=consent` xin scope ngoài policy | Không cấp quyền trái policy |
| Consent phishing dùng domain AS thật | UX/publisher checks và policy giảm khả năng user bị lừa |
| Ngày hết hạn consent record đã qua | Không tự dùng record cũ theo policy |
| User account bị disable nhưng consent vẫn lưu | Không cho phép grant mới chỉ vì consent cũ |
| Redirect URI không đăng ký | Không đưa code hoặc lỗi nhạy cảm tới URI đó |

### 16.5. Những chỉ số nên theo dõi

- Số grant mới theo **client registration, scope/audience, tenant và grant type** (theo chính sách dữ liệu).
- Số yêu cầu scope vượt registration hoặc policy bị từ chối.
- Tỷ lệ user đồng ý/từ chối, hoạt động bất thường của client mới.
- Chênh lệch giữa scopes requested và scopes granted thực tế.
- Số lần role/tenant bị thay đổi và độ trễ vô hiệu quyền tại API.
- Số sự kiện `insufficient_scope` và resource-level DENY, phân loại mà không lộ record.
- Consent revocations, refresh token reuse/revocation và grant token issuance sau khi bị thu hồi.
- Sự kiện access ngoài tenant, repeated object enumeration và export bất thường.

**Không ghi raw access/refresh/ID token, client secret, authorization code hoặc code_verifier** vào log/metrics để điều tra. Ngay cả `sub`, clientId, IP và tenantId có thể là dữ liệu nhạy cảm, cần retention và quyền đọc rõ ràng.

### 16.6. Tách unit test, integration test và authorization test

Unit test của `ConsentPolicy` chỉ chứng minh một hàm xử lý input cụ thể. Cần thêm:

1. **AS integration test:** client registration, issuer, consent state, grant policy và token response thật.
2. **Resource server integration test:** JWT/opaque validation và policy trên DB records/tenant fixtures.
3. **End-to-end test:** client yêu cầu scope, user duyệt/từ chối, AS cấp token đúng quyền, API từ chối resource ngoài quyền.
4. **Negative security test:** issuer khác, token type sai, refresh scope escalation, role revoke, BOLA/IDOR và phishing/consent confusion.

Không dùng token production khi kiểm thử các đường rò query/log; dùng test fixtures, không lưu secret thực trong bản báo cáo.

## 17. Tình huống tự suy luận

### Tình huống A — user đồng ý cho quyền mà mình không có

Alice chỉ có quyền xem chi phí, nhưng Expense Viewer xin `expenses:approve`. Alice nhấn Đồng ý.

**Câu hỏi:** AS có được cấp approve không?

**Đáp án:** Không nếu client/user/organizational policy không cho phép. Consent không làm Alice có thêm quyền nghiệp vụ. AS phải từ chối hoặc chỉ cấp scopes hợp lệ theo contract; RS cũng phải kiểm role/hạn mức/record khi xử lý approve.

### Tình huống B — token hợp lệ, record không thuộc Alice

Alice nhận JWT có chữ ký đúng, `aud=https://expenses.example.com`, `scope=expenses:read`. Cô sửa ID trong URL để đọc khoản chi của Bob.

**Câu hỏi:** API có được trả record của Bob không?

**Đáp án:** Không nếu Alice không có ACL/share/delegation hợp lệ. RS cần kiểm object-level authorization và tenant; consent và scope không thay quyền sở hữu.

### Tình huống C — admin consent từ sai tenant

Admin của tenant A phê duyệt ứng dụng đọc tất cả chi phí tenant B.

**Câu hỏi:** Chức danh admin có đủ không?

**Đáp án:** Không. Thẩm quyền admin phải gắn đúng **tenant và permission** được ủy quyền. Không thể dùng role admin ở tenant A để phê duyệt tài nguyên tenant B.

### Tình huống D — một consent cũ cấp quyền mới

Alice đã chấp thuận `expenses:read` ba tháng trước. Hôm nay client xin thêm `expenses:export` và AS tự dùng lại consent cũ.

**Câu hỏi:** Hợp lệ không?

**Đáp án:** Không nếu scope mới không được chấp thuận/cấp quyền theo policy. Remembered consent phải được ràng buộc với đúng client, subject, scopes/resources, tenant và thời hạn. Scope nhạy cảm mới cần quy trình phù hợp.

### Tình huống E — client dùng `prompt=consent` để xin admin

OIDC client gửi `prompt=consent` và `scope=expenses:admin`, rồi lý luận rằng OP bắt buộc cấp vì đã yêu cầu hiện consent.

**Câu hỏi:** `prompt=consent` có thay policy không?

**Đáp án:** Không. Nó chỉ yêu cầu hành vi tương tác consent theo OIDC; AS vẫn phải kiểm client registration, user/tenant authority và grant policy.

### Tình huống F — role bị gỡ sau khi token được cấp

Alice có role approver và consent lúc 10:00; lúc 10:05 role bị thu hồi nhưng JWT còn hạn đến 10:15.

**Câu hỏi:** `POST /approve` lúc 10:07 có được cho qua?

**Đáp án:** Nếu chính sách yêu cầu quyền approver hiện thời, không. RS phải áp role/business policy ở thời điểm xử lý hoặc có cơ chế state check/TTL đáp ứng độ tươi quyền yêu cầu; không tin claim role cũ vô điều kiện.

### Tình huống G — rút consent nhưng refresh token còn sống

Alice rút quyền Expense Viewer trên UI. Backend vẫn cho refresh token cũ đổi thành access token mới.

**Câu hỏi:** Vấn đề nằm ở đâu?

**Đáp án:** Consent revocation chưa được nối đúng tới grant/refresh-token state theo thiết kế. Cần cập nhật trạng thái AS, chặn refresh khi áp dụng và đánh giá access tokens đang hoạt động.

### Tình huống H — JWT access token chưa hết hạn sau revoke

Sau khi Alice rút consent, RS tiếp tục chấp nhận JWT offline đã phát trước đó đến `exp`.

**Câu hỏi:** Có thể tuyên bố revoke hiệu lực tức thì không?

**Đáp án:** Không nếu hệ thống không có denylist/session version/introspection hoặc cơ chế trạng thái khác. Phải công bố chính sách hiệu lực phù hợp và cân nhắc TTL ngắn hơn cho dữ liệu nhạy cảm.

### Tình huống I — công ty phê duyệt app, service export mọi tenant

Quản trị viên cho phép Expense Viewer ở tenant A. Expense Export Worker dùng token service `expenses:read-all`, trả kết quả từ tenant B khi Alice truyền `tenantId=B`.

**Câu hỏi:** Admin consent có biện minh hành vi này không?

**Đáp án:** Không. Worker là **confused deputy** nếu dùng quyền service mạnh hơn vượt delegated/user/tenant policy. Cần ràng buộc actor, tenant, resource và quyền tại service/data access layer.

### Tình huống J — client có consent nhưng token sai audience

Client dùng access token Expense API để gọi Billing API.

**Câu hỏi:** Billing API có nên chấp nhận chỉ vì user đã đồng ý cho ứng dụng?

**Đáp án:** Không. Mỗi RS phải kiểm audience, issuer và token profile của chính nó. Consent không làm access token trở nên đa dụng cho mọi API.

### Tình huống K — user đồng ý đọc email, app lấy ID token làm quyền API

Ứng dụng nhận ID token OIDC có `sub=alice-123` và `aud=expense-viewer`, rồi gửi nó như bearer token tới Expense API.

**Câu hỏi:** Điều gì sai?

**Đáp án:** ID token chứng minh login cho client, không phải access token dành cho Expense API. RS phải từ chối sai token type/audience; client cần access token được cấp đúng resource/scope.

### Tình huống L — user đồng ý scope rộng, app dùng email làm account key

Một OIDC client nhận `email=alice@example.com` từ OP mới, nối nhầm tới local user cũ dựa trên email, rồi user được xem dữ liệu công ty.

**Câu hỏi:** Consent có sửa được lỗi identity mapping không?

**Đáp án:** Không. User identity cần được xác minh và ràng buộc với `(iss, sub)`; linking giữa các OP phải có bằng chứng và policy. Consent không xác minh cùng một người ở các issuer khác nhau.

### Tình huống M — tài nguyên đổi trạng thái sau khi consent

Alice có quyền sửa khoản chi ở trạng thái DRAFT; khi khoản chi chuyển sang APPROVED, client vẫn gửi PUT sửa số tiền vì token có `expenses:write`.

**Câu hỏi:** API phải xử lý thế nào?

**Đáp án:** Từ chối nếu business policy cấm sửa sau APPROVED. Scope chỉ cho phép xét loại thao tác; trạng thái record quyết định ở thời điểm request.

### Tình huống N — consent phishing trên tên miền AS thật

Alice nhận đường link tới AS chính thức, nhưng client yêu cầu có publisher lạ và xin `expenses:export offline_access`.

**Câu hỏi:** URL đúng domain có đủ để nhấn Đồng ý không?

**Đáp án:** Không. Phải kiểm client/publisher, scope và nhu cầu thật. AS cần giới hạn client registrations, scopes nhạy cảm, admin approval và UX chống lừa đảo. Bấm consent nhầm có thể phát grant thật cho attacker.

### Tình huống O — không hiện consent cho first-party app

Một OP bỏ màn hình consent cho ứng dụng nội bộ đã được tổ chức tin cậy nhưng vẫn kiểm client, scope, subject, audience và resource policy.

**Câu hỏi:** Việc này luôn vi phạm OAuth?

**Đáp án:** Không. OAuth cho phép AS thiết lập authorization qua các cách phù hợp policy mà không bắt popup cho mọi lần. Quan trọng là **điều kiện cấp quyền và bảo vệ dữ liệu vẫn phải đúng**.

### Tình huống P — ứng dụng chỉ xin scope `read` nhưng muốn export

Expense API có hai endpoint `GET /expenses` và `GET /expenses/export`. Client cho rằng `expenses:read` đã chấp thuận thì export hàng loạt mọi tenant cũng được.

**Câu hỏi:** Điều gì cần phân biệt?

**Đáp án:** Quyền export và lượng dữ liệu có thể khác quyền đọc từng record. API cần chính sách cho thao tác export và lọc đúng tenant/ACL. Nếu cần scope khác, AS phải cấp theo policy; không tự suy từ consent `read`.

### Tình huống Q — không có consent trong client credentials

Expense Sync Service dùng `client_credentials` để đồng bộ dữ liệu có thẩm quyền riêng, không có Alice tương tác.

**Câu hỏi:** Thiếu user consent có làm token không hợp lệ?

**Đáp án:** Không. Đây là grant với mô hình authorization của **workload/client**, không phải delegated user consent. AS kiểm workload registration, application permissions, scope/resource và RS kiểm service principal/action.

### Tình huống R — access token có scope đúng nhưng business rule trái

Alice là FINANCE_APPROVER và có token `expenses:approve`; một khoản chi do chính Alice lập nằm dưới hạn mức phê duyệt.

**Câu hỏi:** Có được tự duyệt không?

**Đáp án:** Không nếu separation-of-duties policy cấm. Role, scope và consent cùng hợp lệ vẫn chưa đáp ứng điều kiện **not own expense**.

## 18. Ứng cứu khi consent hoặc issuance policy bị lạm dụng

Nếu phát hiện AS đã cấp scope vượt policy hoặc ứng dụng nhận consent bằng cách giả mạo, cần đánh giá **grant và dữ liệu đã bị truy cập**, không chỉ sửa text consent screen.

### 18.1. Trình tự xử lý

1. **Khoanh vùng:** issuer, client registration, subjects/tenants, scopes/resources, thời điểm bắt đầu và loại grant.
2. **Chặn phát hành tiếp:** sửa registration/policy, tạm dừng client hoặc scope nhạy cảm theo quy trình ứng cứu.
3. **Kiểm trạng thái consent/grant:** xác định user/admin approval có hợp lệ và đủ thẩm quyền không.
4. **Thu hồi khi phù hợp:** revoke refresh tokens/grants, áp cơ chế chặn access token đang hoạt động nếu cần/khả thi.
5. **Xem dữ liệu API:** audit những khoản chi, exports, updates hoặc approvals đã diễn ra.
6. **Kiểm tra service accounts:** xác định confused deputy hay quyền workload quá rộng.
7. **Khắc phục UX và cấu hình:** verified publisher, scope descriptions, consent binding, client allowlists.
8. **Thêm regression tests:** scope escalation, cross-tenant access, dynamic role revocation, API BOLA.
9. **Thông báo theo quy trình:** nếu có rò dữ liệu, làm việc với bảo mật/pháp lý và người chịu trách nhiệm.

### 18.2. Tại sao chỉ sửa consent record là chưa đủ?

~~~text
Consent record = REVOKED

Nhưng có thể còn:
    refresh token ACTIVE
    JWT access token chưa hết exp
    job export đang chạy
    dữ liệu đã được app bên thứ ba tải về
    session được tạo từ login cũ
~~~

Một record consent chỉ là **một phần vòng đời quyền**. Phải nối được audit từ **client + subject + grant → token issuance → API access → business actions** bằng metadata bảo vệ; không lưu raw token làm audit key.

### 18.3. Redaction trong điều tra

Không ghi nguyên:

~~~text
Authorization: Bearer <ACCESS_TOKEN>
refresh_token=<SECRET>
id_token=<SIGNED_JWT>
authorization_code=<CODE>
code_verifier=<SECRET>
client_secret=<SECRET>
~~~

Có thể ghi theo chính sách:

~~~text
traceId
issuerId
clientId
grantId (opaque internal identifier, không phải secret)
subjectReference (được bảo vệ)
tenantId
requestedScopeCategory
grantedScopeCategory
resourceType / action
authorizationDecision=ALLOW|DENY
denialReasonCategory
policyVersion
timestamp
~~~

Subject identifiers, IP, tenant và scopes có thể là dữ liệu nhạy cảm; retention và quyền đọc phải tuân thủ mục đích vận hành, không xem hash không khóa là vô danh hoàn toàn.

### 18.4. Quy trình rollback phải tránh tạo lại lỗ hổng

Khi một policy được tăng cường đột ngột khiến client cũ lỗi, không nên “sửa nhanh” bằng cách bỏ authorization check hoặc cấp broad scope. Thay vào đó:

- Phân loại client/tenant/endpoint bị ảnh hưởng.
- Cấu hình ngoại lệ có phê duyệt và **giới hạn quyền + thời hạn** nếu thực sự cần.
- Giữ audit và monitoring.
- Ưu tiên nâng cấp client để xin scope hợp lệ.
- Test đầy đủ trước khi khôi phục lưu lượng.

**Tính sẵn sàng của sản phẩm không được giải quyết bằng cách biến consent thành wildcard authorization policy.**

## 19. Checklist thiết kế consent đúng vai trò

Trước khi đưa một OAuth/OIDC integration vào production:

1. **Định nghĩa rõ consent:** user/admin đang đồng ý điều gì, client nào và các quyền/tài nguyên nào? Có phải một UX authorization hay nghĩa vụ privacy riêng?
2. **Client registration:** grant types, redirect URIs, client authentication methods, allowed scopes và allowed resources/audiences được xác định ở AS.
3. **User/administrator authority:** người bấm đồng ý có được quyền ủy quyền phạm vi đó không? Admin chỉ được duyệt trong tenant/quyền được cấp?
4. **Consent binding:** decision liên kết với đúng subject/session, client, scopes, resources, tenant, authorization request và hiệu lực.
5. **No silent escalation:** remembered consent không cho scope mới, tenant mới hay client khác ngoài phạm vi; user bấm đồng ý không tạo permission.
6. **Flow security:** Authorization Code + PKCE S256 khi áp dụng, issuer/state/redirect binding, confidential client authentication và code single-use.
7. **Token issuance:** AS chỉ phát subject/client/scope/audience theo granted policy, không copy request parameters trực tiếp vào token.
8. **Token type:** OIDC ID token, OAuth access token và refresh token đúng mục đích; không hoán đổi credential ở API.
9. **Resource server:** xác minh issuer, audience, thời gian, signature/introspection, token type/profile, scope và trạng thái.
10. **Business authorization:** kiểm tra principal, action, resource ID, owner/ACL, tenant, role, hạn mức và trạng thái hiện tại.
11. **Operations:** export, batch, search, background jobs và downstream services thực thi cùng boundary quyền như API trực tiếp.
12. **Dynamic policy:** có cơ chế phù hợp khi role/membership/ACL đổi sau token issuance; kiểm tra độ tươi quyền theo threat model.
13. **Revocation:** consent revocation được nối tới grant/refresh-token lifecycle; hành vi access token còn hạn được hiểu và công bố chính xác.
14. **Refresh:** không mở rộng scope, audience hoặc subject qua refresh; rotation hoặc sender constraint cho public client khi được cấp refresh token theo security BCP.
15. **Privacy:** consent UI chính xác, không tự xem OAuth approval là đồng ý xử lý mọi mục đích; bảo vệ dữ liệu claims và logs.
16. **Phishing:** verified publisher/client name, mô tả scope dễ hiểu, cảnh báo kết nối lạ và kiểm soát application registrations.
17. **Logging:** không ghi raw codes, verifier, client secret, access/refresh/ID tokens; audit decision metadata có quyền truy cập rõ.
18. **Negative tests:** scope escalation, admin sai tenant, BOLA/IDOR, role revoked, token sai audience, consent replay, token/refresh reuse.
19. **Error handling:** phân biệt AS consent denial, token error, API 401 và API 403; không phản chiếu secrets và dữ liệu tài nguyên bị từ chối.
20. **Incident response:** có cách khoanh vùng grant/token/API activity và xử lý dữ liệu đã truy cập, không chỉ sửa consent record.

### 19.1. Sơ đồ quyết định cuối cùng

~~~mermaid
flowchart TD
    A[Client xin quyền] --> B{Client/grant/resource được AS cho phép?}
    B -- Không --> X[Từ chối]
    B -- Có --> C{Subject hoặc workload đủ authority theo policy?}
    C -- Không --> X
    C -- Có --> D{Có consent/approval hợp lệ nếu yêu cầu?}
    D -- Không --> X
    D -- Có --> E[AS phát token theo grant đã giới hạn]
    E --> F[Client gọi resource server]
    F --> G{Token hợp lệ và dành cho API này?}
    G -- Không --> Y[401 hoặc lỗi xác thực phù hợp]
    G -- Có --> H{Scope/grant cho phép loại action?}
    H -- Không --> Z[403 hoặc lỗi authorization phù hợp]
    H -- Có --> I{Principal/action/resource/tenant/context được phép?}
    I -- Không --> Z
    I -- Có --> J[ALLOW trong giới hạn policy]
~~~

Sơ đồ minh họa một delegated flow. Trong **client credentials** hoặc grant không có End-User, nút consent được thay bằng **chính sách authorization workload/application** phù hợp. Nó không được biến thành “không có consent nên không cần policy”.

### 19.2. Quy tắc ngắn để ghi nhớ

~~~text
Consent:
    Người dùng / admin có chấp thuận yêu cầu cụ thể không?

Authorization Server:
    Client, grant, subject, scopes và audience có được phép cấp không?

Access token:
    AS đã cấp credential nào, cho API nào, trong bao lâu?

Resource Server:
    Caller có được làm ACTION này với RESOURCE này, trong CONTEXT này?

Kết luận:
    CONSENT ≠ AUTHORIZATION POLICY
    ACCESS TOKEN VALID ≠ RESOURCE ACCESS ALLOWED
    SCOPE PRESENT ≠ OWNERSHIP VERIFIED
~~~

**Kết luận:** OAuth consent là một phần của quy trình **thông báo và chấp thuận** quyền truy cập phù hợp, **không phải giấy phép vượt qua authorization policy**. Authorization Server phải giới hạn grant theo client, subject, scope, audience, tenant và chính sách tổ chức; Resource Server phải tiếp tục kiểm token và **quyền trên từng hành động/tài nguyên cụ thể**. Khi quyền thay đổi hoặc consent bị rút lại, token/refresh/grant có vòng đời riêng cần được xử lý. Một hệ thống an toàn phải xem consent là **một tín hiệu trong chuỗi quyết định tin cậy**, không bao giờ là nút “Allow everything”.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Server, authorization grant, scope, authorization request/response và token issuance.
- [RFC 6749 §3.1 — Authorization Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.1): cách AS xác định quyền người dùng, chấp thuận yêu cầu hoặc dùng phương thức authorization khác theo chính sách.
- [RFC 6749 §3.3 — Access Token Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): scope trong request/response và giới hạn cấp quyền.
- [RFC 6749 §6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh token không được xin scope vượt grant ban đầu.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): chống token leakage/replay, bảo vệ grant và authorization flow.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization header và lỗi `invalid_token`/`insufficient_scope`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, claims và token validation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): scope/resource/audience trong authorization request và token issuance.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange, actor/delegation và token cho resource downstream.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): yêu cầu quyền chi tiết hơn scopes khi áp dụng theo profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái và metadata opaque access tokens.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): giao thức thu hồi token.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256 bảo vệ authorization code.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `openid`, ID token, UserInfo, `prompt=consent`/`prompt=none` và `consent_required`.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): JWT/opaque token validation ở Java APIs.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): pre/post authorization và kiểm soát method-level.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): authorization consent, client registration, token endpoint và custom policy/validation.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): tại sao object ID phải được kiểm quyền dù token hợp lệ.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): default deny, least privilege và object-level authorization.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth client, scope, redirect/PKCE và bảo vệ token.
