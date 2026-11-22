# 17.1 Phân biệt xác thực danh tính với quyết định phân quyền trong ứng dụng

## Mục tiêu

Sau bài này, bạn có thể:

1. Trả lời rõ hai câu hỏi bảo mật khác nhau: **Authentication — “Bạn là ai?”** và **Authorization — “Bạn có được thực hiện hành động này đối với tài nguyên cụ thể này, trong ngữ cảnh hiện tại không?”**
2. Hiểu JAAS (**Java Authentication and Authorization Service**) trong Java 17, đặc biệt **LoginContext**, **LoginModule**, **Configuration**, **CallbackHandler**, **Subject**, **Principal**, các pha **login/commit/abort/logout**.
3. Phân biệt việc **LoginContext.login() thành công** với quyết định cho phép đọc hóa đơn, sửa hồ sơ, gọi API quản trị hay truy cập tài nguyên thuộc tenant khác.
4. Thiết kế authorization kiểm tra **actor + action + resource + context**, áp dụng **deny-by-default**, **least privilege**, **tenant isolation** và kiểm tra **quyền ở từng object** thay vì chỉ kiểm tra đăng nhập hoặc vai trò.
5. Chạy ví dụ Java 17+ có **LoginModule tùy chỉnh**, Subject nhận một Principal sau khi xác thực, và **policy của ứng dụng** từ chối truy cập sai tenant/chủ sở hữu dù người gọi đăng nhập hợp lệ.
6. Nhận biết quan hệ giữa JAAS Authorization truyền thống với **Java Security Manager/Policy** trong tài liệu cũ; hiểu vì sao không được coi **Subject.doAs** là cơ chế phân quyền nghiệp vụ tự động trên các JDK hiện đại.
7. Xây test và audit đúng cho các trường hợp **chưa xác thực**, **đã xác thực nhưng không đủ quyền**, **quyền bị thu hồi**, **mạo danh**, **IDOR/BOLA** và **session context bị trộn**.

**Ý chính:** Xác thực cho ứng dụng một **identity đã được kiểm chứng qua cơ chế đáng tin**; phân quyền là **một quyết định khác, lặp lại tại từng ranh giới tài nguyên và thao tác**. **Đã đăng nhập không đồng nghĩa được phép làm mọi việc.** JAAS có cả các API và tài liệu authorization lịch sử, nhưng **kết quả authentication không tự động cấp quyền nghiệp vụ** cho mọi invoice, tenant, database row hoặc API.

## 1. Hai câu hỏi: Authentication và Authorization

### 1.1 Authentication — xác thực danh tính

**Authentication (AuthN)** trả lời: một thực thể (người dùng, máy chủ, service hoặc tiến trình) có thực sự chứng minh được identity mà nó đang khai báo hay không?

Ví dụ bằng chứng:

- Mật khẩu được xác minh theo đúng password verifier có salt và KDF phù hợp.
- Token/session đã được xác thực chữ ký/MAC, issuer, audience, hiệu lực và ràng buộc cần thiết.
- Private key chứng minh qua mTLS hoặc một giao thức ký thách thức đúng.
- Kerberos ticket được xác minh theo cơ chế JAAS/GSS-API.
- MFA/passkey, theo chính sách của identity provider và application.

Sau khi chứng cứ hợp lệ, hệ thống có thể lập một **authentication context**: user ID ổn định, cơ chế xác thực, thời điểm, độ tin cậy, tenant được liên kết, session ID và các claim đã kiểm chứng. Không có bằng chứng hợp lệ thì **không được tự nhận actor theo dữ liệu do client gửi**.

Ví dụ:

~~~text
HTTP request
Authorization: Bearer <token>

   Token/credential validation
       |
       +--- Không hợp lệ ---> Reject (chưa được xác thực)
       |
       +--- Hợp lệ --------> Authenticated identity:
                             userId = "alice"
                             authMethod = "oidc"
                             session = ...
~~~

**Authentication không nói Alice có được xem hóa đơn số 127 của Bob.** Nó chỉ nói hệ thống có cơ sở tin người gọi là Alice theo quá trình kiểm tra tương ứng.

### 1.2 Authorization — quyết định quyền trên tài nguyên

**Authorization (AuthZ)** trả lời: actor đã được xác thực (hoặc một public/anonymous actor được chính sách cho phép) có quyền thực hiện **một action** trên **một resource** trong **một context** không?

Mô hình:

~~~text
Authorize(
    actor    = Alice,
    action   = "invoice:read",
    resource = Invoice 127,
    context  = {tenant: "tenant-A", time, authStrength, ...}
)
    => ALLOW hoặc DENY
~~~

Policy có thể yêu cầu đồng thời:

- Alice đã được xác thực từ một nguồn tin.
- Alice có quyền **INVOICE_READER** theo role/permission store đáng tin.
- Invoice 127 thuộc **tenant-A** và Alice có membership hợp lệ với tenant này.
- Alice là **owner** hoặc được ủy quyền đọc tài nguyên đó.
- Invoice chưa bị khóa/tịch thu hoặc có các trạng thái nghiệp vụ cho phép đọc.
- Phiên còn hiệu lực, MFA gần đây hoặc thiết bị đạt điều kiện nếu thao tác nhạy cảm.
- Không có explicit deny/thu hồi quyền nào vượt các điều kiện allow.

Nếu một điều kiện bắt buộc không đạt, kết quả phải là **DENY**.

### 1.3 Authentication và Authorization độc lập nhưng liên quan

| Khía cạnh | Authentication (AuthN) | Authorization (AuthZ) |
| --- | --- | --- |
| Câu hỏi | Ai đang gọi? Bằng chứng identity hợp lệ? | Actor này được làm gì, với tài nguyên nào, lúc nào? |
| Dữ liệu đầu vào | Credential, session/token, client certificate, challenge | Identity đã xác thực, policy/role, tenant, quyền đối tượng, context |
| Thành phần điển hình | LoginContext/LoginModule, IdP, session verifier | Authorization service, policy decision point, ACL/RBAC/ABAC/ReBAC |
| Kết quả | Identity đáng tin hoặc thất bại | ALLOW/DENY cho một action/resource |
| Thời điểm | Khi đăng nhập hoặc xác minh request/session | **Mỗi thao tác/tài nguyên nhạy cảm**; có thể có cache ngắn hạn theo policy |
| Thay đổi thường gặp | Logout, hết phiên, token sai, MFA | Vai trò đổi, quyền bị thu hồi, resource đổi owner, chuyển tenant |
| Sai lầm | Chấp nhận userId do client khai | Cho phép vì user đã login mà không kiểm tra object-level access |
| Bảo mật | Ngăn giả mạo identity | Ngăn vượt quyền, xem nhầm dữ liệu, leo thang quyền và cross-tenant access |

**Một tài nguyên công khai có thể được truy cập không cần login** nếu policy cố ý cho phép actor anonymous thực hiện action cụ thể. Ngược lại, ngay cả admin đã xác thực cũng **không nhất thiết được quyền đọc mọi dữ liệu** nếu chính sách quy định ranh giới tenant, phân tách nhiệm vụ hoặc dữ liệu đặc biệt.

### 1.4 Ví dụ ngắn: login thành công vẫn bị từ chối

~~~text
Alice đăng nhập đúng mật khẩu            -> AuthN: SUCCESS
Alice mở invoice do Alice sở hữu          -> AuthZ: ALLOW (nếu policy cho phép)
Alice mở invoice thuộc tenant-B           -> AuthZ: DENY
Alice sửa cấu hình hệ thống chỉ admin      -> AuthZ: DENY
Alice vừa bị thu hồi vai trò invoice.read  -> AuthZ: DENY ở lần check tiếp theo
~~~

**AuthN thành công + AuthZ thất bại là hành vi hoàn toàn bình thường và phải được kiểm thử.**

## 2. JAAS xuất hiện ở đâu trong câu chuyện này?

**JAAS** là thành phần trong Java SE cho cơ chế **xác thực có thể cắm nhiều provider/module**. JAAS còn có mô hình **authorization dựa trên Subject/Principal** tích hợp với hệ thống permission/security policy Java truyền thống. Vì vậy sẽ sai nếu nói “JAAS chỉ có authentication và không hề có authorization”; nhưng cũng sai nếu nói “JAAS login tự cấp quyền API”.

Trong ứng dụng hiện đại, cần phân biệt rõ:

- **JAAS authentication layer**: xác định và kiểm chứng identity, xây Subject/Principals theo module được cấu hình.
- **Authorization policy của ứng dụng**: quyết định user/service được thực hiện action trên resource cụ thể hay không.
- **Lịch sử JAAS permission-based authorization**: dùng Subject/Principal, Subject.doAs, AccessControlContext, Policy và Security Manager trong kiến trúc Java cũ; **không phải lớp kiểm tra RBAC/tenant nghiệp vụ tự động**.

### 2.1 Những class/interface chính của JAAS

| API | Trách nhiệm |
| --- | --- |
| **javax.security.auth.login.LoginContext** | Điều phối đăng nhập theo tên cấu hình, gọi LoginModule; login/logout và lấy Subject |
| **javax.security.auth.login.Configuration** | Chọn LoginModule nào, thứ tự, control flag và options của từng module |
| **javax.security.auth.spi.LoginModule** | Xác thực theo cơ chế cụ thể: Kerberos, password backend, smartcard, v.v. |
| **javax.security.auth.callback.CallbackHandler** | Cung cấp câu trả lời cho Callback (tên, mật khẩu, PIN...), tách UI/source credential khỏi module |
| **NameCallback / PasswordCallback** | Phương tiện truyền tên và mật khẩu cho LoginModule |
| **javax.security.auth.Subject** | Tập các Principal/credentials liên quan đến một thực thể đã hoặc đang được xác thực |
| **java.security.Principal** | Danh tính/thuộc tính nhận dạng được biểu diễn bằng đối tượng có getName() |
| **AppConfigurationEntry** | Tên LoginModule, control flag và options trong cấu hình |
| **LoginException / FailedLoginException** | Báo thất bại login/module; ứng dụng không chấp nhận identity khi login thất bại |

Một Subject có thể có **nhiều Principal** đại diện những danh tính/kiểu nhận dạng khác nhau. Ví dụ account user, Kerberos principal và nhóm/danh tính khác. Không được mặc định rằng Subject chỉ có một Principal hoặc mọi Principal đều là **role**.

### 2.2 Luồng JAAS authentication điển hình

~~~text
Ứng dụng gọi LoginContext("appName")
              |
        Đọc Configuration
              |
       Chọn một hoặc nhiều LoginModule
              |
    LoginModule.initialize(subject, callbackHandler,
                           sharedState, options)
              |
    LoginModule.login()     -> xác thực credential
              |
       Thành công toàn cục?
          /              \
        NO                YES
        |                  |
  abort()/exception   commit() của modules
        |                  |
    Không tin          Subject chứa Principals /
    danh tính          credentials được module thêm
                           |
                       LoginContext.getSubject()
                           |
                Application authentication context
                           |
                   Authorization trên từng request
~~~

**Hai pha quan trọng:**

1. **login()**: module xác minh bằng chứng identity, giữ trạng thái tạm trong module; chưa nên thêm Principal vào Subject trước khi biết toàn bộ authentication đã thành công.
2. **commit()**: sau khi các module cần thiết vượt qua, module thêm Principal/credential thích hợp vào Subject. Nếu toàn bộ login fail, hệ thống gọi **abort()** để dọn trạng thái; **logout()** dùng để dọn các thông tin module đã commit.

Việc Subject chứa một Principal được tạo từ một module đáng tin sau LoginContext.login() thành công **có ý nghĩa identity**. Nó không tự chứng minh actor được xem mọi object.

### 2.3 Configuration và control flag

Một file cấu hình JAAS theo cú pháp truyền thống có thể như sau:

~~~text
BusinessApp {
    com.example.auth.CompanyLoginModule required;
    com.example.auth.AdditionalCheckModule requisite;
};
~~~

Đây là **minh họa cấu hình**, không thể chạy nếu các class com.example... chưa có trong ứng dụng. Tên lớp và options phải trỏ tới LoginModule hợp lệ.

Các flag của JAAS:

| Flag | Vai trò |
| --- | --- |
| **REQUIRED** | Module cần thành công; dù module thất bại vẫn tiếp tục xử lý những module tiếp theo, cuối cùng login thất bại |
| **REQUISITE** | Module cần thành công; thất bại khiến việc đánh giá dừng ngay |
| **SUFFICIENT** | Nếu thành công và các REQUIRED/REQUISITE trước nó không thất bại, có thể kết thúc login sớm; nếu thất bại tiếp tục module khác |
| **OPTIONAL** | Thành công/thất bại có thể không quyết định tổng thể; nếu không có module bắt buộc thì cần ít nhất một module tùy chọn/đủ điều kiện thành công |

Các flag điều khiển **kết quả xác thực hợp thành**, **không phải** quyền “invoice:read”, “admin:write” hay membership tenant.

**Sai cấu hình JAAS** có thể vô tình khiến một module yếu trở thành đường đăng nhập thay thế cho module mạnh. Nhưng kể cả cấu hình login đúng, authorization trên tài nguyên vẫn phải tự kiểm tra.

## 3. Subject, Principal và claim: không phải quyền cấp sẵn

### 3.1 Principal là identity, không phải permission toàn cục

**Principal** là một đối tượng biểu diễn một danh tính được gắn với Subject. Việc Principal có tên “alice” không có ý nghĩa “Alice được đọc tất cả bảng hóa đơn”.

Ví dụ:

~~~text
Subject:
  Principals:
    UserPrincipal("alice")
    KerberosPrincipal("alice@EXAMPLE.TEST")
  PublicCredentials:   ...
  PrivateCredentials:  ... (có thể chứa bí mật)
~~~

Đây là **biểu diễn khái niệm**, không phải output cố định của JAAS. Các module/provider thực sự có loại Principal riêng.

Subject có thể chứa credentials nhạy cảm. Đừng đưa toàn bộ **Subject.toString()**, getPrivateCredentials() hoặc raw ticket/token vào log/response. Thu thập chỉ những thông tin được phép phục vụ audit (userId, mechanism, session reference, outcome).

### 3.2 Có một Principal trong object chưa đủ chứng minh đã đăng nhập

Một **Subject có thể được tạo/chỉnh sửa bằng code Java** trong các ngữ cảnh được phép. Do đó code không nên tin bất kỳ Subject object hoặc chuỗi Principal nào **được client tùy ý cung cấp** là bằng chứng login.

Một sự kiện “đã xác thực” phải đến từ **đường kiểm tra credential/token có tin cậy**. Khi service tự tạo identity từ header:

~~~text
X-User-Id: admin
X-Role: OWNER
X-Tenant: tenant-A
~~~

mà không xác minh header có đến từ một upstream identity gateway đã xác thực và được bảo vệ khỏi spoofing, kẻ gọi bên ngoài có thể tự chọn identity/role. Tương tự, **new UserPrincipal("admin")** trong một lớp request không tạo đặc quyền nào ngoài những gì code sai có thể tự gán.

**Quy tắc:** chỉ lấy authenticated principal từ một ranh giới được kiểm soát như JAAS login thành công, framework security context được chứng thực, hoặc token/session verifier hợp lệ.

### 3.3 Khi nào role/nhóm trong Principal hoặc JWT có thể dùng?

Một hệ thống JAAS/IdP có thể gắn **group/role/claim** vào Subject hoặc token. Nhưng ứng dụng cần quyết định:

- Nguồn nào được phép phát hành các role/claim đó?
- Claim đã được kiểm chứng chữ ký/issuer/audience/timestamp chưa?
- Claim có đúng **tenant, application, resource, audience** hiện tại?
- Role có hết hạn/đã bị thu hồi không?
- Role có đủ cho action trên object cụ thể không?
- Quyền có bị explicit deny, ownership, separation-of-duties hoặc policy khác hạn chế?

**Role đã xác thực là đầu vào của authorization policy**, không phải mọi lúc là quyết định allow tự động. Ví dụ “MANAGER” của tenant-A không có nghĩa được xem tài liệu bí mật của tenant-B.

### 3.4 Authentication strength và step-up

Một số thao tác cần điều kiện mạnh hơn chỉ “đã đăng nhập”: MFA gần đây, thiết bị quản lý, phiên chưa vượt thời gian, mạng/vùng địa lý được cấp phép hoặc phê duyệt hai người. Đó là **điều kiện context** của authorization.

Ví dụ:

~~~text
Alice đã login bằng mật khẩu hôm qua.
Action: đổi thông tin nhận tiền của doanh nghiệp.

Policy:
  user đã xác thực
  AND có quyền billing:update
  AND thuộc đúng tenant
  AND MFA step-up trong 5 phút gần đây
  AND tài khoản không bị khóa
=> nếu thiếu MFA mới: yêu cầu step-up, không cho UPDATE ngay.
~~~

**Không nhầm yêu cầu MFA** (bước tăng độ tin cậy của xác thực) với **quyền nghiệp vụ**. Hai điều kiện có thể phải đồng thời đúng.

## 4. Mô hình quyết định quyền cho ứng dụng Java

Thiết kế một điểm kiểm tra logic:

~~~text
AUTHZ(actor, action, resource, context):
    nếu actor chưa xác thực và resource không public:
        DENY

    lấy chính sách/role/tenant từ nguồn đáng tin
    tải resource đúng tenant/owner và trạng thái
    áp dụng explicit deny & business constraints
    chỉ ALLOW nếu tất cả điều kiện bắt buộc đạt
    còn lại DENY
~~~

**Deny-by-default** nghĩa là không có rule cho phép rõ thì từ chối. Không viết:

~~~text
if (user != null) {
    return ALLOW;
}
~~~

đối với mọi thao tác nhạy cảm. User được xác thực là **điều kiện đầu**, không phải toàn bộ chính sách.

### 4.1 Actor + action + resource + context

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| **Actor** | userId "alice", tenant membership | Người thật sự đang yêu cầu |
| **Action** | invoice.read, invoice.approve, invoice.delete | Mỗi thao tác có quyền khác nhau |
| **Resource** | invoice ID 127, tenant-A, owner alice | Quyền phải gắn với object cụ thể |
| **Context** | trạng thái hóa đơn, MFA age, thời gian, môi trường | Quyết định phụ thuộc điều kiện hiện tại |
| **Policy** | role grant + owner + tenant + explicit deny | Tách quy tắc khỏi code chỉ xử lý HTTP |
| **Decision** | ALLOW/DENY + reason code nội bộ | Dễ test/audit, không tiết lộ nhạy cảm |

Một người được **invoice.read** không nhất thiết được **invoice.delete** hoặc **invoice.approve**. Một tài nguyên public cũng có thể chỉ được đọc, không được sửa.

### 4.2 RBAC: role-based access control

RBAC cấp permission cho **vai trò**, vai trò gắn với actor:

~~~text
Role INVOICE_READER -> invoice:read
Role INVOICE_EDITOR -> invoice:read, invoice:update
Role AUDITOR        -> invoice:read (trong phạm vi được giao)
~~~

RBAC hữu ích vì dễ quản trị, nhưng không tự xử lý đủ ranh giới object/tenant:

- Alice có role INVOICE_READER trong tenant-A.
- Invoice X thuộc tenant-B.
- RBAC role check một mình có thể ALLOW sai.
- **Tenant check** phải bổ sung, và có thể thêm owner, purpose hoặc resource ACL.

### 4.3 ABAC: attribute-based access control

ABAC dùng thuộc tính của actor, resource, action và môi trường:

~~~text
allow if
    actor.active
    AND actor.tenantId == resource.tenantId
    AND action == "invoice.read"
    AND "INVOICE_READER" in actor.permissions
    AND resource.status != "SEALED"
~~~

Không tin attribute từ request khi attribute đó phải do server kiểm soát. Ví dụ **tenantId** gửi trong URL chỉ là **target identifier**, không có nghĩa người gọi là member của tenant đó. Kiểm tra membership từ directory/token đáng tin và trạng thái database.

### 4.4 ReBAC: relationship-based access control

ReBAC dựa trên quan hệ giữa actor và resource:

~~~text
Alice --owns--> Invoice 127
Bob   --reviewer-of--> Invoice 127
Carol --member-of--> Team Finance --owns--> Folder F
~~~

Nó đặc biệt hữu ích với tài nguyên có owner/share/team hierarchy. Nhưng vẫn phải kiểm tra nguồn quan hệ và tình huống revoke; không dùng một danh sách ID do client gửi làm bằng chứng.

### 4.5 ACL, capability và các mô hình khác

- **ACL** trên tài nguyên định nghĩa ai hoặc nhóm nào có quyền; cần bảo vệ việc cập nhật ACL.
- **Capability token** có thể trao quyền truy cập tài nguyên cụ thể khi được xác thực và giới hạn rõ ràng, ví dụ signed short-lived download URL. Capability phải có phạm vi/expiry/audience thích hợp.
- **Policy-as-code/authorization service** có thể tập trung quyết định; bản thân policy engine không bảo vệ endpoint nếu backend quên gọi nó.

Bạn có thể kết hợp RBAC + ABAC + ReBAC; không phải chọn đúng một mô hình mới an toàn.

## 5. Phân quyền theo object: chống IDOR/BOLA và rò tenant

Một sai lầm nghiêm trọng:

~~~text
GET /api/invoices/127
    |
Security filter: "User đã login? YES"
    |
db.findInvoiceById(127)
    |
return invoice
~~~

Nếu hóa đơn 127 thuộc Bob hoặc tenant-B, Alice có thể truy xuất bằng cách đoán ID. Đây là một dạng **Broken Object Level Authorization (BOLA)** / **Insecure Direct Object Reference (IDOR)**.

Phiên bản đúng:

~~~text
GET /api/invoices/127
    |
AuthN: xác thực identity Alice
    |
AuthZ: Alice có invoice:read trong tenant-A?
    |
Data layer: lấy invoice 127 trong tenant được phép
    |
AuthZ: owner/ACL/status của object có cho Alice đọc?
    |
ALLOW -> serialize đúng field được phép
DENY  -> trả lỗi theo chính sách, không lộ dữ liệu
~~~

**Lưu ý:** kiểm tra quyền ở đầu request là cần nhưng chưa đủ nếu quyền thay đổi hoặc resource bị chuyển owner giữa lần check và lần sử dụng. Với transaction quan trọng, gắn điều kiện vào truy vấn cập nhật, transaction hoặc cơ chế lock/version phù hợp.

### 5.1 Query bị thiếu tenant filter

Code không an toàn:

~~~java
// Ví dụ anti-pattern; không phải chương trình Java độc lập.
Invoice invoice = repository.findById(request.invoiceId());
return invoice;
~~~

Có thể sửa theo pattern:

~~~java
// Ví dụ minh họa, phụ thuộc repository và actor context.
Invoice invoice = repository.findByIdAndTenantId(
        request.invoiceId(), authenticatedActor.tenantId());
authorization.requireCanRead(authenticatedActor, invoice);
return invoice;
~~~

Với nhiều tenant có thể dùng cùng danh sách role, thiếu tenant condition trong truy vấn làm rò dữ liệu. Chỉ role-check ở controller rồi gọi findById không tự tạo tenant isolation.

### 5.2 Admin role cũng có phạm vi

Quyền **ADMIN** có thể có scope:

- Admin trong một project;
- Admin trong tenant-A;
- Tenant administrator;
- System administrator;
- Compliance reader chỉ đọc;
- Break-glass account theo quy trình đặc biệt.

Không dùng một boolean **isAdmin** toàn cục nếu policy thực tế có nhiều phạm vi; đây là nguyên nhân hay gặp của **privilege escalation**.

## 6. Ví dụ Java 17+ hoàn chỉnh: JAAS login + kiểm tra quyền riêng

Ví dụ này dùng **một chương trình tự chứa**. Nó thể hiện:

1. **LoginContext** nạp **DemoLoginModule** qua Configuration do Java code tạo, thay vì cần file cấu hình ngoài.
2. **CallbackHandler** đưa username/password cho LoginModule.
3. **LoginModule.login()** xác minh credential đào tạo, còn **commit()** mới thêm UserPrincipal vào Subject.
4. Sau xác thực, **canRead(...)** là **chính sách ứng dụng độc lập**, lấy role/tenant từ một directory nội bộ mô phỏng và kiểm tra **tenant + owner** của hóa đơn.
5. Test Alice được xem hóa đơn của mình; bị chặn khi chuyển tenant hoặc chủ sở hữu, dù login thành công.
6. **logout()** xóa Principal mà module đã thêm. Login sai mật khẩu bị từ chối.

**Giới hạn an toàn:** Credential **test-only** được hardcode để làm ví dụ chạy độc lập. **Tuyệt đối không dùng LoginModule này trong production**. Không có password hashing, user store thật, rate limiting, MFA, session manager hoặc audit. Directory Map cố định là **mô phỏng dữ liệu quyền từ backend đáng tin**, không phải nguồn claim do browser truyền vào.

### 6.1 Code độc lập: JaasDecisionDemo.java

Tạo tệp **JaasDecisionDemo.java** bằng UTF-8:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public class JaasDecisionDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override
        public String getName() { return name; }
    }

    public record Invoice(String tenant, String owner) { }

    public record Entitlement(
            Set<String> roles, Set<String> tenants) { }

    // Provider xác thực đào tạo: không dùng mật khẩu hardcode trong production.
    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal user;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                               Map<String, ?> sharedState,
                               Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) {
                throw new LoginException("No callback handler");
            }

            NameCallback name = new NameCallback("Username: ");
            PasswordCallback pass =
                    new PasswordCallback("Password: ", false);
            char[] received = null;

            try {
                handler.handle(new Callback[]{name, pass});
                received = pass.getPassword();

                if (!"alice".equals(name.getName())
                        || received == null
                        || !Arrays.equals(received,
                            new char[]{'t','e','s','t','-',
                                       'o','n','l','y'})) {
                    throw new FailedLoginException(
                            "Invalid credentials");
                }
                user = new UserPrincipal("alice");
                loggedIn = true;
                return true;
            } catch (IOException | UnsupportedCallbackException e) {
                throw new LoginException("Cannot obtain credentials");
            } finally {
                pass.clearPassword();
                if (received != null) {
                    Arrays.fill(received, '\0');
                }
            }
        }

        @Override
        public boolean commit() throws LoginException {
            if (!loggedIn) return false;
            if (subject.isReadOnly()) {
                throw new LoginException("Read-only Subject");
            }
            subject.getPrincipals().add(user);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            user = null;
            loggedIn = false;
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(user);
            }
            committed = false;
            loggedIn = false;
            user = null;
            return true;
        }
    }

    private static CallbackHandler credentials(
            String name, char[] secret) {
        return callbacks -> {
            for (Callback cb : callbacks) {
                if (cb instanceof NameCallback n) {
                    n.setName(name);
                } else if (cb instanceof PasswordCallback p) {
                    p.setPassword(secret);
                } else {
                    throw new UnsupportedCallbackException(cb);
                }
            }
        };
    }

    // Configuration nằm trong code để chương trình độc lập và dễ chạy.
    private static Configuration config() {
        return new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"demo".equals(name)) return null;
                return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(
                        DemoLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };
    }

    // Giả lập entitlement store SERVER-SIDE đáng tin.
    // Không xây Map này từ user-supplied request/header.
    private static final Map<String, Entitlement> directory = Map.of(
        "alice", new Entitlement(
                Set.of("INVOICE_READER"), Set.of("tenant-A"))
    );

    // QUYẾT ĐỊNH PHÂN QUYỀN ỨNG DỤNG, KHÔNG PHẢI LOGIN.
    private static boolean canRead(
            Subject authenticated, Invoice invoice) {
        if (authenticated == null || invoice == null) return false;

        Set<UserPrincipal> users =
                authenticated.getPrincipals(UserPrincipal.class);
        if (users.size() != 1) return false;

        UserPrincipal user = users.iterator().next();
        Entitlement rights = directory.get(user.getName());

        return rights != null
                && rights.roles().contains("INVOICE_READER")
                && rights.tenants().contains(invoice.tenant())
                && invoice.owner().equals(user.getName());
    }

    public static void main(String[] args) throws Exception {
        char[] goodSecret = "test-only".toCharArray();
        LoginContext login = new LoginContext(
            "demo", null,
            credentials("alice", goodSecret), config());

        login.login();               // AuthN thành công.
        Arrays.fill(goodSecret, '\0');

        Subject subject = login.getSubject();
        System.out.println("JAAS authenticated: "
                + subject.getPrincipals(UserPrincipal.class)
                        .contains(new UserPrincipal("alice")));

        System.out.println("Own invoice allowed: "
                + canRead(subject, new Invoice("tenant-A", "alice")));

        System.out.println("Cross-tenant denied: "
                + !canRead(subject, new Invoice("tenant-B", "alice")));

        System.out.println("Other owner denied: "
                + !canRead(subject, new Invoice("tenant-A", "bob")));

        login.logout();
        System.out.println("Principals removed on logout: "
                + subject.getPrincipals(UserPrincipal.class).isEmpty());

        char[] badSecret = "wrong".toCharArray();
        LoginContext badLogin = new LoginContext(
            "demo", null,
            credentials("alice", badSecret), config());

        boolean rejected = false;
        try {
            badLogin.login();
        } catch (LoginException expected) {
            rejected = true;
        } finally {
            Arrays.fill(badSecret, '\0');
        }
        System.out.println("Wrong password rejected: " + rejected);
    }
}
~~~

Chương trình dùng **record** và pattern matching **instanceof**, đều là tính năng chuẩn trong **Java 17**. Class **DemoLoginModule** là lớp public static nằm trong class public bên ngoài, có constructor public không đối số mặc định, cho phép LoginContext khởi tạo module bằng tên class được Configuration cung cấp.

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 JaasDecisionDemo.java
java JaasDecisionDemo
~~~

Stdout dự kiến:

~~~text
JAAS authenticated: true
Own invoice allowed: true
Cross-tenant denied: true
Other owner denied: true
Principals removed on logout: true
Wrong password rejected: true
~~~

**Giải thích từng bước:**

1. **JAAS authenticated: true:** LoginModule nhận callback, xác minh username/password demo, commit UserPrincipal("alice") vào Subject; LoginContext.login() trả về bình thường.
2. **Own invoice allowed: true:** policy canRead nhìn entitlement server-side Alice có role INVOICE_READER, membership tenant-A và owner Alice, nên cho phép.
3. **Cross-tenant denied: true:** Alice vẫn đăng nhập nhưng invoice thuộc tenant-B, không đạt điều kiện membership.
4. **Other owner denied: true:** Invoice thuộc tenant-A nhưng owner Bob, còn chính sách ví dụ yêu cầu actor là owner.
5. **Principals removed on logout: true:** LoginModule.logout() bỏ UserPrincipal mà module đã thêm.
6. **Wrong password rejected: true:** một LoginContext khác được đưa mật khẩu sai, login() thất bại và không tạo authenticated context hợp lệ.

**Tất cả kiểm tra quyền trong ví dụ nằm ở canRead(...), không phải LoginModule.login().** Việc tách hàm minh họa ranh giới trách nhiệm: module xác minh “Alice là ai”, policy service quyết định “Alice có được đọc object này không”.

### 6.2 Vì sao demo dùng một Map directory thay vì Principal role?

Map **directory** đại diện database/identity directory đáng tin của ứng dụng. Dù một LoginModule thực có thể thêm **RolePrincipal** từ nguồn tin, ví dụ muốn minh họa rằng **authorization không chỉ nhìn một claim hoặc đã login**.

Trong production, directory cần:

- Cập nhật role, trạng thái membership và quyền được ủy quyền từ backend quản trị.
- Kiểm tra tenant/project scope, resource owner, ACL và explicit deny.
- Có chính sách cache/TTL/invalidation để hạn chế quyền đã thu hồi vẫn được dùng.
- Phân tách nguồn role đáng tin với dữ liệu user đưa vào form/header/URL.
- Không chấp nhận người dùng tự sửa Map/policy hoặc tạo Subject tùy ý để bỏ qua LoginContext.

### 6.3 Những gì demo chưa làm được

Ví dụ được cố tình giới hạn:

- Không có user DB, password hash, salt, MFA, session cookie, JWT hoặc OIDC.
- Mật khẩu đào tạo **test-only** hardcode, không an toàn cho production.
- AuthZ policy cố định, không load từ database thực, không có TTL/cache/revoke.
- Invoice chỉ là record gồm tenant và owner; không có ID, status, ACL, amount.
- Không làm HTTP server, không thực hiện input validation, CSRF/XSS/CORS hay audit storage.
- Không giải quyết concurrency hoặc TOCTOU khi quyền/object thay đổi giữa kiểm tra và ghi DB.
- Subject trong demo được tạo qua đường đăng nhập do ứng dụng tin. **Bản thân Java Subject không phải một security boundary nếu mã không đáng tin có thể tự tạo/chỉnh nó**.
- **LoginContext.logout() không hủy mọi API token, session cookie hoặc quyết định quyền đã cache** ở một lớp khác. Quản lý session/revocation là trách nhiệm bổ sung của ứng dụng.

Không lấy ví dụ làm “template đăng nhập production” bằng cách thay chuỗi password thật vào source; hãy dùng cơ chế danh tính được duy trì/kiểm định và framework security phù hợp.

## 7. Đưa AuthN/AuthZ vào request pipeline

Một pipeline web/API lý tưởng phân tách trách nhiệm rõ ràng:

~~~text
Client Request
      |
[Transport / TLS / input-size and syntax validation]
      |
[Authentication Filter]
  validate session / JWT / mTLS / JAAS-backed mechanism
      |
      +--> no valid identity -> reject or public policy
      |
[Trusted Authentication Context]
  actorId, authMethod, tenant memberships, session metadata
      |
[Authorization Decision]
  actor + action + resource + context + current policy
      |
      +--> DENY --> reject; no read/write side effect
      |
[Business Service]
  enforce resource-level policy close to data operation
      |
[Repository / DB]
  tenant-scoped query + transaction/row-level guard
      |
[Response]
  expose only fields within approved scope
~~~

**Không tin rằng mọi API controller đều sẽ nhớ kiểm tra quyền**. Hãy đặt policy enforcement ở lớp dùng chung (method boundary/service/repository) và có integration tests để phát hiện endpoint nào bỏ sót kiểm tra.

Tuy nhiên, một security filter chỉ có thể kiểm tra “người gọi đăng nhập hợp lệ” **không thể tự quyết định quyền với object chưa được load**. Nhiều ứng dụng cần kiểm tra coarse-grained ở route và **fine-grained sau khi biết resource**.

### 7.1 AuthN context phải đúng cho từng request

Với thread pool, async tasks, messaging hoặc reactive pipelines, cần tránh **principal của request A bị dùng nhầm cho request B**. Dù framework có thread-local security context, không được mặc định nó được sao chép đúng qua CompletableFuture, executor, callback hoặc message consumer.

An toàn hơn:

- Truyền authentication context **đã được kiểm tra** vào nơi cần sử dụng theo cơ chế được framework hỗ trợ.
- Ở consumer của queue, xác thực service/producer hoặc xác minh message provenance trước khi nhận actor context.
- Không dùng biến static global currentUserId.
- Dọn context khi request kết thúc và kiểm thử cross-request isolation.
- Không tin userId/tenantId được gửi qua job payload nếu chưa có ràng buộc/quyền phù hợp.

### 7.2 401, 403 và 404

Đối với HTTP API, các mã thường dùng:

- **401 Unauthorized**: request thiếu hoặc chưa có chứng cứ xác thực hợp lệ; có thể kèm challenge WWW-Authenticate theo giao thức.
- **403 Forbidden**: server đã hiểu request, identity có thể hợp lệ, nhưng policy **không cho phép** action/resource.
- **404 Not Found**: có thể được dùng theo chính sách để **không tiết lộ sự tồn tại** của tài nguyên mà actor không có quyền biết.

Việc chọn 403 hay 404 nhằm tránh object enumeration cần **nhất quán**, nhưng không thay thế kiểm tra quyền thật. Không trả nội dung nhạy cảm rồi mới đổi HTTP status thành 403; side effect đã xảy ra.

Với API JSON, đừng trả chi tiết private policy, danh sách role bị thiếu của người khác hoặc tên tài nguyên không được phép trong thông báo lỗi. Ghi reason code nội bộ ở mức kiểm soát, không tiết lộ qua response.

## 8. Xác thực thành công nhưng phiên hoặc quyền đã thay đổi

### 8.1 Logout không đồng nghĩa thu hồi tất cả phiên ở mọi hệ thống

**LoginContext.logout()** gọi logout các LoginModule và dọn các Principal/credential mà module quản lý. Nó **không tự vô hiệu** một access token JWT đã phát hành, không xóa server-side session store bên ngoài, không gửi thông báo thu hồi role tới các service khác và không xóa authz cache một cách kỳ diệu.

Hệ thống có thể cần:

- Session invalidation và cookie deletion đúng.
- Token expiry/refresh rotation/revocation phù hợp threat model.
- Cập nhật quyền theo nguồn tin sau khi role/membership bị thu hồi.
- Audit user/session logout và xử lý multi-device.
- CSRF protection đối với session cookie khi tương ứng.
- Xử lý các background jobs đang giữ principal/entitlements đã cũ.

### 8.2 Quyền có thể bị thu hồi giữa hai request

~~~text
10:00 Alice login thành công.
10:01 Alice được quyền invoice:read tenant-A.
10:05 Admin thu hồi quyền invoice:read của Alice.
10:06 Alice gửi request mới đọc invoice.

AuthN có thể vẫn VALID (session còn).
AuthZ phải đọc quyết định theo quyền hiện hành/policy cache hợp lệ:
       DENY.
~~~

Nếu toàn hệ thống chỉ đọc role tại lúc login rồi cache vô thời hạn, quyền đã thu hồi có thể tiếp tục được dùng. Thiết kế freshness phù hợp với sensitivity: cache ngắn hạn, version/policy epoch, event invalidation hoặc kiểm tra nguồn authoritative cho action nhạy cảm.

**Không đồng nhất expiry của chứng cứ xác thực với expiry của entitlement**. Hai thời điểm có thể khác nhau.

### 8.3 Token chứa role không bảo đảm role còn hiệu lực mãi

JWT hoặc token ký có thể mang claim roles/permissions; sau khi verify, chúng là claim **được issuer công bố tại thời điểm phát hành**, không chắc phản ánh mọi thay đổi kể từ đó. Phải xét:

- Token lifetime và rotation/revocation.
- Audience, issuer, signature/MAC và thuật toán được phép.
- Tenant scope và resource scope.
- Có cần kiểm tra entitlement động cho dữ liệu nhạy cảm không?
- Giao thức nào cho phép service tin upstream identity context?

**Không đọc payload JWT bằng Base64 decoder rồi tin claim mà không xác minh chữ ký, issuer/audience/expiry**. Base64 chỉ là cách biểu diễn, không xác thực.

## 9. Legacy JAAS authorization và giới hạn trên Java hiện đại

### 9.1 JAAS từng hỗ trợ principal-based access control

Tài liệu JAAS Authorization của Java SE 17 mô tả cách sử dụng **Subject/Principal** cùng **java.security.Policy**, **AccessControlContext**, **Subject.doAs** và **Security Manager** để kiểm tra các permission trong sandbox Java truyền thống.

Ý tưởng lịch sử:

~~~text
Authenticated Subject
        |
   Subject.doAs(subject, action)
        |
AccessControlContext gắn Subject/Principals
        |
Security Manager + Policy quyết định Permission
        |
Java runtime có thể chặn thao tác được bảo vệ
~~~

Đây là mô hình **truy cập API/tài nguyên Java theo permission policy** thuộc kiến trúc Security Manager, **không tự tương đương** với policy kiểu “Alice được xóa invoice nào của tenant nào”.

### 9.2 Java 17 và JDK 24+ cần phân biệt

- **Java 17:** Security Manager bị **deprecated for removal** theo JEP 411. Một số API JAAS authorization truyền thống vẫn hiện diện và các tutorial cũ vẫn mô tả chúng.
- **JDK 18+:** nhiều API phụ thuộc AccessControlContext/Security Manager như Subject.doAs bị đánh dấu deprecated for removal, có API chạy với Subject khác trong đời sau.
- **JDK 24+:** theo **JEP 486**, Security Manager **bị vô hiệu hóa vĩnh viễn**; không thể bật lại bằng property startup hoặc cài custom SecurityManager như trước. Các đường kiểm tra quyền dựa trên Security Manager không còn là nền tảng đáng tin để bảo vệ tài nguyên.
- **JAAS authentication APIs không vì vậy mà đồng loạt biến mất**. LoginContext, LoginModule và Subject vẫn có vai trò với các công nghệ cần cơ chế xác thực pluggable, tùy JDK/provider.

Vì vậy **không thiết kế một hệ thống phân quyền REST/API mới chỉ dựa trên Subject.doAs + java.policy với kỳ vọng JDK tương lai tự ngăn dữ liệu cross-tenant**. Thay vào đó, làm **authorization check tường minh ở service/repository/policy layer**, với enforcement có test và quan sát được.

### 9.3 Subject.doAs không tự thực hiện requirePermission

Ngay cả trong code Java cũ:

~~~java
// Minh họa ý tưởng legacy; KHÔNG phải code khuyến nghị
// cho cơ chế phân quyền API mới trên JDK 24+.
Subject.doAs(subject, (java.security.PrivilegedAction<Void>) () -> {
    readSomeResource();
    return null;
});
~~~

Code trên **không tự chứa điều kiện kiểm tra quyền invoice/tenant**. Tác dụng permission-based còn phụ thuộc policy, Security Manager và API tạo ra permission checks đúng. Không được suy diễn:

~~~text
"Chạy dưới Subject của Alice"
           =>
"Alice tự động không xem được invoice của Bob"
~~~

Đó là suy luận **sai** đối với authorization nghiệp vụ nếu bạn không thực hiện riêng rule kiểm tra object.

### 9.4 Có nên dùng Principal như role không?

Một framework có thể xây **RolePrincipal** hoặc **GroupPrincipal**, nhưng cần rõ:

- Module nào có thẩm quyền khẳng định role?
- Role có ràng buộc tenant và expiry không?
- Có quyền truy cập object riêng hay không?
- Chỗ nào của code thật sự thực hiện **require** quyền?
- Khi Principal bị bỏ đi/đổi, session/policy cache có còn giữ quyền cũ không?

**Principal là dữ liệu identity/security context, không tự là policy enforcement point.** Không dựa vào class name hoặc getName() tùy ý như một security check hoàn chỉnh.

## 10. Bảo vệ tài nguyên ở lớp service và DB

### 10.1 Check gần nơi thực hiện hành động

Ví dụ dịch vụ chuyển tiền:

~~~text
POST /transfers
   -> authn hợp lệ
   -> authz account.transfer trên account nguồn
   -> xác minh owner/membership từ DB
   -> kiểm tra trạng thái account, hạn mức, MFA
   -> trong transaction xác nhận điều kiện vẫn đúng
   -> ghi transfer & audit
~~~

Không chỉ check endpoint là “có role TRANSFER_USER” rồi cho caller truyền **fromAccountId** của bất kỳ người nào. Nhiều lỗi nghiêm trọng bắt nguồn từ **IDOR trong thao tác ghi**, chứ không chỉ đọc.

### 10.2 TOCTOU: Time of Check vs Time of Use

Giả sử service:

1. Kiểm tra Alice là owner invoice.
2. Một request khác chuyển owner hoặc thu hồi membership.
3. Service vẫn UPDATE invoice vì đã check xong.

Nếu action cần bảo đảm nhất quán, cách tiếp cận có thể là:

- Thực hiện policy check và UPDATE trong **cùng transaction** với isolation phù hợp.
- Gắn điều kiện tenant/owner/status vào **UPDATE ... WHERE ...**; kiểm tra affected row count.
- Dùng optimistic locking/version để tránh thay đổi state ngoài dự đoán.
- Đọc lại entitlement hoặc policy epoch tại điểm commit khi cần.
- Không dùng cached role/owner quá lâu cho thao tác quan trọng.

Cách chính xác phụ thuộc DB và mô hình cạnh tranh; điều cốt lõi là **không để kết quả kiểm tra quyền cũ bị tách rời khỏi thao tác bảo vệ**.

### 10.3 Field-level authorization

Một actor được xem Invoice không nhất thiết được xem mọi trường:

~~~text
Invoice:
  id, date, status, amount            -> reader thông thường
  customerPersonalId, bankAccount     -> cần permission nhạy cảm
  internalRiskNotes, fraudFlags       -> compliance only
~~~

Sau object-level allow, response serialization có thể phải **lọc field** theo policy. Đừng trả toàn bộ object entity từ ORM rồi hy vọng front-end ẩn trường bằng CSS.

### 10.4 Multi-tenant data access

Trong hệ thống SaaS:

- Mọi read/list/update/delete phải thực thi tenant boundary.
- Tenant header/subdomain/URL chỉ xác định **tenant được yêu cầu**, không chứng minh membership.
- Dữ liệu policy/role có thể phụ thuộc tenant.
- Background jobs/scheduled workflows cũng cần actor/service authorization, không được bypass vì “nội bộ”.
- DB row-level security (RLS), tenant-scoped repository và API authorization có thể hỗ trợ nhau; không coi một lớp là lý do bỏ hết lớp khác.

## 11. Logging và lỗi phải thể hiện đúng sự khác biệt

### 11.1 Log authn và authz riêng

Các sự kiện gợi ý:

~~~text
AUTHN_SUCCESS user=alice mechanism=JAAS sessionRef=...
AUTHN_FAILURE reasonCode=INVALID_CREDENTIALS ...
AUTHZ_ALLOW actor=alice action=invoice.read resource=127 tenant=A
AUTHZ_DENY  actor=alice action=invoice.read resource=127 reasonCode=TENANT_SCOPE
AUTHZ_DENY  actor=alice action=invoice.update reasonCode=MISSING_PERMISSION
~~~

Đây là **minh họa log structure**, không phải dữ liệu thật và không phải định dạng bắt buộc. Ở production, tránh ghi password, access token, private credentials, raw Subject, session secret, PII nhạy cảm, hay giá trị resource mà caller không có quyền biết. Quy định correlation ID, thời hạn lưu, phân quyền log và phát hiện xâm nhập.

**Không phân biệt cụ thể “username không tồn tại” và “password sai” trong phản hồi đăng nhập công khai** nếu việc đó giúp user enumeration. Có thể lưu reason code nội bộ thích hợp.

### 11.2 Authz denial không phải login failure

Nếu Alice đăng nhập hợp lệ mà bị chặn invoice:delete, không nên tự động báo **“invalid password”** hoặc logout người dùng chỉ vì action không được phép. Xử lý đúng là **authorization denied** cho action đó, trừ khi có dấu hiệu session compromise hoặc chính sách rủi ro yêu cầu bước khác.

Phân biệt giúp support, audit và test không bị sai tín hiệu.

## 12. Test matrix thiết yếu

| Test case | AuthN | AuthZ | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không có cookie/token và endpoint yêu cầu login | FAIL | Không cấp quyền | 401/challenge theo giao thức |
| Login sai password demo | FAIL | Không tạo actor tin cậy | Không được truy cập protected resource |
| Login đúng với Alice | PASS | Chưa được quyết định cho object | Có authenticated Subject/context |
| Alice đọc invoice tenant-A do Alice sở hữu | PASS | ALLOW | Đọc được field đã cấp quyền |
| Alice đọc invoice tenant-B | PASS | DENY | Không trả dữ liệu |
| Alice đọc invoice của Bob cùng tenant-A | PASS | DENY theo policy ví dụ | Không trả dữ liệu |
| Alice không có role editor nhưng gọi invoice:update | PASS | DENY | Không cập nhật |
| Alice có role reader nhưng chưa được cấp MFA step-up cần thiết | PASS | DENY hoặc yêu cầu step-up | Không tiến hành hành động nhạy cảm |
| Alice có session còn hạn nhưng role vừa bị thu hồi | PASS | DENY sau khi policy cập nhật có hiệu lực | Quyền thay đổi không bị bỏ qua |
| Client gửi X-User-Id: admin mà không có trust boundary | FAIL | Không tin header | Không mạo danh |
| Caller tự tạo Subject/Principal không qua login tin cậy | Không chứng minh identity | Không chấp nhận | Không nâng quyền |
| Object đổi owner giữa check và write | PASS | Phải được kiểm tra nhất quán | Không ghi nếu điều kiện không còn đúng |
| User được đọc invoice nhưng không được xem bankAccount | PASS | Object ALLOW, field DENY | Response không rò field |
| Service/queue consumer không có actor context hợp lệ | FAIL hoặc theo service identity policy | DENY nếu policy đòi caller | Không chạy như admin mặc định |
| Logout JAAS, nhưng session store ngoài còn tồn tại | Trạng thái tùy kiến trúc | Revoke session đúng | Không đánh đồng logout với invalidation toàn hệ |
| Một developer quên gọi authz ở endpoint mới | PASS | Không được phép bypass | Integration/security test thất bại |

### 12.1 Test trực tiếp quyền ở các tầng

Đừng chỉ test service function với boolean **isAdmin=true**. Nên kiểm tra:

- Policy đơn vị với actor/action/resource/context kết hợp hợp lệ và bất hợp lệ.
- Endpoint integration: login và quyền object, status/response/body, không có side effect khi deny.
- Database query/transaction: tenant scope, row count, race ownership/permission changes.
- Multi-tenant negative tests: cùng ID nhưng khác tenant, ID đoán được, list/export endpoints.
- Role revocation và expired sessions.
- Async message/job propagation và cross-request context leakage.
- Audit events không chứa secrets.
- Unauthorized field serialization và bulk endpoints.

Bài test quan trọng là **“đã xác thực nhưng không được quyền”**, vì nhiều API chỉ kiểm tra trường hợp “chưa đăng nhập” và bỏ sót object-level policy.

## 13. Những sai lầm phổ biến và cách sửa

1. **“LoginContext.login() không ném exception nên mọi API đều ALLOW.”** Sai; cần AuthZ trên từng action/resource.
2. **“Principal có tên admin nên là admin toàn hệ thống.”** Sai; phải kiểm tra nguồn role, scope và chính sách.
3. **“Có role USER thì được đọc mọi user.”** Sai; cần owner/ACL và tenant scoping.
4. **“Client gửi tenantId nên đó là tenant membership của họ.”** Sai; membership phải tới từ backend/token đáng tin.
5. **“Dùng Subject.doAs là JAAS sẽ tự chặn SQL SELECT sai tenant.”** Sai; cần policy enforcement cụ thể.
6. **“Security Manager còn hoạt động như cũ trên mọi JDK.”** Sai; JDK 24+ đã vô hiệu hóa vĩnh viễn.
7. **“Để admin bypass toàn bộ check cho nhanh.”** Rủi ro vượt quyền; cần phân biệt admin scope, break-glass và audit.
8. **“Role lúc login không bao giờ đổi.”** Sai; cần xử lý revoke/freshness.
9. **“Đã có JWT signed nên resource ID trong URL chắc hợp lệ.”** Sai; JWT identity không tự cấp quyền object.
10. **“Mọi trường invoice đều được trả vì người gọi được invoice.read.”** Sai; có thể cần field-level authorization.
11. **“Service nội bộ không cần authz.”** Sai; service principal cũng cần least privilege và tenant scope.
12. **“Lấy user từ thread-local bất kỳ async task nào cũng đúng.”** Sai; context propagation và dọn sạch phải được kiểm chứng.
13. **“Chỉ controller cần check, repository không cần tenant filter.”** Sai; nhiều code path có thể bypass controller.
14. **“Kiểm tra quyền xong thì ghi DB bao giờ cũng được.”** Sai trong race/TOCTOU; cần transaction và điều kiện tương ứng.
15. **“Logout LoginContext chắc chắn revoke JWT bên IdP.”** Sai; session/token lifecycle độc lập.
16. **“Các permission Java Policy trong tutorial cũ là thay thế tương đương cho API RBAC.”** Không; chức năng và trạng thái Security Manager đã khác.
17. **“401 và 403 dùng thay nhau được.”** Không; lỗi nhận dạng khác lỗi thiếu quyền, dù policy có thể trả 404 khi cần che resource.
18. **“Authz DENY nên in hết mọi claim, resource và policy cho client biết.”** Sai; chỉ log tối thiểu có phân quyền và tránh rò dữ liệu.
19. **“Endpoint list có tenant filter, endpoint export/bulk thì không cần.”** Sai; mọi đường đọc dữ liệu phải enforce scope.
20. **“LoginModule tự quyết định invoice nào Alice được đọc.”** Không phù hợp phân tách trách nhiệm; module xác thực, service policy đánh giá resource/action.

## 14. Câu hỏi ôn tập

**Câu 1.** Xác thực và phân quyền khác nhau thế nào?

**Trả lời:** Xác thực kiểm tra actor thực sự là ai; phân quyền kiểm tra actor có được làm action này trên resource cụ thể trong context hiện tại hay không.

**Câu 2.** LoginContext.login thành công có tự cấp quyền invoice.read không?

**Trả lời:** Không. Cần chính sách quyền từ nguồn đáng tin và kiểm tra resource-level scope.

**Câu 3.** LoginModule.commit có vai trò gì?

**Trả lời:** Khi login toàn cục đạt điều kiện, commit thêm Principal/credential liên quan vào Subject; login phase trước đó chỉ kiểm chứng credential và giữ trạng thái tạm.

**Câu 4.** Subject chứa UserPrincipal("alice") có chắc Alice đã login không?

**Trả lời:** Chỉ khi Subject đến từ authentication flow được server tin và chưa bị mạo danh/tamper; Subject object tự tạo không phải bằng chứng mật mã.

**Câu 5.** Vì sao role INVOICE_READER không đủ để xem invoice tenant-B?

**Trả lời:** Role có thể được cấp trong tenant-A; phải kiểm tra tenant/resource scope và owner/ACL khác.

**Câu 6.** RBAC khác ABAC ra sao?

**Trả lời:** RBAC dùng role→permission; ABAC kiểm tra thuộc tính actor/resource/action/context. Có thể kết hợp với ReBAC để bảo vệ object.

**Câu 7.** Tại sao code chỉ tìm invoice theo ID dễ bị BOLA/IDOR?

**Trả lời:** User đã đăng nhập có thể đoán ID của tài nguyên người khác; phải kiểm tra owner/tenant/ACL trước khi trả dữ liệu.

**Câu 8.** Có cần đánh giá quyền lại sau khi user vừa bị thu hồi role?

**Trả lời:** Có. Chính sách cache/revalidation phải phản ánh thu hồi trong thời gian thích hợp với độ nhạy của action.

**Câu 9.** Subject.doAs có tự bảo vệ mọi resource của ứng dụng không?

**Trả lời:** Không. Mô hình permission-based JAAS lịch sử phụ thuộc Policy/Security Manager và các permission checks; JDK 24 đã disable Security Manager. API nghiệp vụ cần authorization enforcement tường minh.

**Câu 10.** Logout JAAS có tự hủy một JWT đang có ngoài hệ thống không?

**Trả lời:** Không. Token/session manager và policy revocation là trách nhiệm hệ thống liên quan.

**Câu 11.** HTTP 401 và 403 thường được dùng thế nào?

**Trả lời:** 401 khi thiếu/chưa có authentication hợp lệ; 403 khi không được phép thực hiện thao tác. Có thể dùng 404 theo chính sách che sự tồn tại tài nguyên.

**Câu 12.** Vì sao authz cần actor/action/resource/context chứ không chỉ username?

**Trả lời:** Quyền phụ thuộc vào việc đang làm gì, object thuộc ai/tenant nào, trạng thái nào và điều kiện hiện tại; username đơn lẻ không quyết định được.

**Câu 13.** Một admin tenant-A có thể đọc dữ liệu tenant-B không?

**Trả lời:** Không mặc nhiên. Admin thường có scope; quyền global chỉ tồn tại khi policy đã cho phép rõ và có kiểm soát.

**Câu 14.** Authentication có thể chưa cần cho tài nguyên nào?

**Trả lời:** Với resource/action được chính sách xác định là public, anonymous actor có thể được cho phép; không có nghĩa mọi action trên cùng resource là public.

**Câu 15.** Vì sao cần test race giữa check quyền và update DB?

**Trả lời:** Resource owner/membership có thể đổi sau check; transaction, row condition, locking/version giúp giữ quyết định phù hợp thời điểm sử dụng.

## 15. Checklist triển khai

- [ ] Có nguồn **identity** đáng tin (JAAS LoginModule/IdP/session verifier).
- [ ] Tách AuthN context khỏi AuthZ decision; không tin userId/role từ header không bảo vệ.
- [ ] Có mapping rõ **actor → roles/permissions theo scope**, quản lý bằng backend có thẩm quyền.
- [ ] Định nghĩa policy cho từng **action/resource**, bao gồm public access có chủ đích.
- [ ] **Default DENY** khi thiếu actor/policy/tenant/ownership.
- [ ] Kiểm tra **object-level** và **field-level** khi cần, không chỉ route-level.
- [ ] Mọi read/list/update/delete/export/bulk endpoint đều enforce tenant scope.
- [ ] Dữ liệu quyền bị thu hồi có thời hạn hiệu lực, cache invalidation hoặc kiểm tra nguồn đáng tin.
- [ ] Check và hành động ghi quan trọng được bảo vệ khỏi TOCTOU.
- [ ] Async/thread/queue context không làm rò principal giữa người dùng.
- [ ] Xử lý session/token/JAAS logout đúng theo từng tầng.
- [ ] Logging phân biệt authn failure và authz denial, không ghi credentials/Subject nhạy cảm.
- [ ] Không dựa vào **SecurityManager/Subject.doAs** như bộ máy RBAC mới cho REST API.
- [ ] Có test **đã login nhưng bị từ chối**, cross-tenant, missing role, impersonation, revoke, field leak.
- [ ] Triển khai least privilege ở service, DB, network và secret store.

## 16. Tài liệu chính thức để tra cứu

- [Oracle Java SE 17 — JAAS Authentication](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication.html): giải thích pluggable authentication, LoginContext, Subject, Principal.
- [Oracle Java SE 17 — JAAS Authentication Tutorial](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication-tutorial.html): luồng login với JAAS.
- [Oracle Java SE 17 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): các pha login/commit/abort/logout và CallbackHandler.
- [Oracle Java SE 17 — JAAS Authorization](https://docs.oracle.com/en/java/javase/17/security/jaas-authorization.html): authorization legacy dựa trên Principal và Java permission policy.
- [Oracle Java SE 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): constructor, login, getSubject, logout.
- [Oracle Java SE 17 — Configuration API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): các flag REQUIRED/REQUISITE/SUFFICIENT/OPTIONAL.
- [Oracle Java SE 17 — Subject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): Principal và credential sets.
- [OpenJDK JEP 411](https://openjdk.org/jeps/411): deprecate Security Manager trong Java 17.
- [OpenJDK JEP 486](https://openjdk.org/jeps/486): permanently disable Security Manager từ JDK 24.
- [Oracle JDK 24 — Security Manager Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): tác động tới các API permission/security legacy.

## Kết luận

**Xác thực danh tính là điểm khởi đầu, không phải giấy phép toàn quyền.** JAAS có thể xác thực người dùng/service qua LoginContext và LoginModule, đặt Principal/credential đáng tin vào Subject. Nhưng ứng dụng vẫn phải đánh giá **actor, action, resource và context** theo policy rõ ràng, kiểm tra scope/tenant/owner/ACL cùng thời điểm sử dụng và mặc định từ chối khi điều kiện không đủ.

**JAAS authorization dựa trên Java Security Manager là một cơ chế lịch sử có giới hạn lớn trên JDK hiện đại**, không thay thế cho phân quyền nghiệp vụ. Với Java 17+ và các service có REST API, thực hiện policy enforcement tường minh, kiểm thử các tình huống người dùng đã login nhưng **không đủ quyền**, và quản lý session/role revocation thay vì chỉ kiểm tra LoginContext.login().
