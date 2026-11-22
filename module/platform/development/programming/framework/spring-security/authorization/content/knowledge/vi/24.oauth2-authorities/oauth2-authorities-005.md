# Phân biệt quyền ứng dụng với quyền của người dùng trong OAuth2 và Spring Security

## 1. Vì sao một access token hợp lệ vẫn có thể đại diện sai chủ thể?

Một ứng dụng doanh nghiệp có các luồng gọi API khác nhau:

- Alice đăng nhập cổng tài liệu, bấm đọc một tài liệu của chính mình.
- Một dịch vụ báo cáo chạy ban đêm, tự lấy token để tổng hợp dữ liệu được doanh nghiệp cấp phép.
- Một backend nhận request của Alice, rồi gọi dịch vụ tài liệu thay Alice.
- Một ứng dụng tích hợp bên thứ ba được quản trị viên cấp quyền quản lý một số nguồn dữ liệu.
- Bob có vai trò ADMIN trong tenant A, nhưng chỉ có VIEWER trong tenant B.

Tất cả có thể sử dụng `Authorization: Bearer ...`, nhưng **không có nghĩa access token nào cũng đại diện cho một người dùng đang đăng nhập**. OAuth2 phân biệt các hành vi cấp quyền:

1. **Delegated / user-delegated access**: một ứng dụng được ủy quyền thực hiện thao tác **thay mặt một người dùng** đã tham gia vào luồng cấp quyền.
2. **Application-only / app-only access**: ứng dụng hoặc service được cấp quyền **với tư cách chính nó**, không phải như một người dùng cụ thể.

Khi resource server nhận một token, cần xác định đúng **principal của lời gọi**, **ứng dụng client**, **quyền token được cấp**, **tenant/resource** và **chính sách nghiệp vụ**. Nếu một backend dùng token `client_credentials` của mình để truy cập dữ liệu "của Alice" chỉ vì request chứa `userId=alice`, rất dễ trở thành **confused deputy**: ứng dụng được cấp quyền rộng bị lợi dụng để làm thay việc caller không được làm.

**Mục tiêu bài học**: phân biệt các loại quyền ở mức khái niệm và hiện thực bằng Spring Security Resource Server/OAuth2 Client, đưa ra chính sách riêng cho tác nhân USER và APPLICATION, thử nghiệm với Java 17+, phân biệt token scopes/roles với business authorization, và phát hiện lỗi vượt quyền trong các luồng service-to-service hoặc on-behalf-of.

## 2. Bốn vai trò OAuth2 không được đánh đồng

Theo OAuth2, hệ thống có thể gồm:

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Resource owner** | Chủ thể có quyền cấp phép truy cập tài nguyên, thường là user trong luồng delegated | Alice |
| **Client** | Ứng dụng muốn truy cập tài nguyên qua API | web-portal, reporting-bot |
| **Authorization server** | Xác thực/cấp phép theo grant và phát access token | IdP/authorization service |
| **Resource server** | API nhận token, kiểm tra tính hợp lệ và quyết định cấp quyền theo tài nguyên | document-api |

Một client **không nhất thiết là resource owner**. Trong `client_credentials`, client có thể lấy access token cho **chính nó**. Trong `authorization_code`, có user tham gia, nhưng access token vẫn có thể chỉ có **scopes API** chứ không chứa toàn bộ business roles, owner relationships hoặc current ACL.

Điều này dẫn đến bốn câu hỏi tách biệt:

```text
WHO is calling?          -> user, application, or a verified delegation?
WHICH client is involved? -> client_id / authorized party
WHAT token allows?       -> scopes, permissions, audience, validity
WHAT resource permits?   -> tenant, owner, ACL, policy, state and action
```

Một token có `scope=documents.read` thường chứng minh rằng authorization server đã cấp một **phạm vi được phép gọi API**. Nó không tự chứng minh Document 42 thuộc Alice, không bị xóa, được chia sẻ cho Alice hoặc nằm trong tenant có membership hợp lệ.

## 3. User-delegated và app-only: bảng so sánh cốt lõi

| Thuộc tính | Quyền của người dùng (delegated) | Quyền ứng dụng (app-only) |
| --- | --- | --- |
| Chủ thể hành động | Có user thực sự trong ngữ cảnh ủy quyền | Client/service/application |
| Grant thường gặp | Authorization Code + PKCE, hoặc một delegated/token-exchange flow được phép | Client Credentials |
| Có user login? | Thường có, theo luồng cấp quyền | Không bắt buộc, thông thường không |
| Quyền OAuth | Những delegated scopes user/client được cấp | Những scopes/roles/app permissions dành cho client |
| Hạn chế nghiệp vụ | User membership, role, ACL, tenant, resource owner **và** scopes | App identity, app grant, tenant/resource scope **và** scopes |
| Audit chủ thể | User ID, client ID, authorization context | Client/service ID, optional initiator *nếu được xác minh riêng* |
| Dữ liệu được xem | Theo phạm vi được giao và quyền user thực | Theo quyền service/app được chủ quản cấp riêng |
| Có thể "lấy quyền user" mặc định? | Không; phải có delegation đúng | **Không**; không có user ngầm |
| Thay đổi chính sách | Thay role/ACL user có thể làm quyền giảm | Thu hồi grant/role/app assignment làm quyền giảm |
| Các rủi ro | User token bị dùng sai audience, role bleed, IDOR | Confused deputy, quá rộng, mọi request dùng cùng bot token |

Một lệnh `GET /me` thường cần **người dùng được xác minh**. App-only token không nên tự được gán user mặc định hay người sở hữu service. Một endpoint `POST /internal/reports/rebuild` có thể chấp nhận **chỉ service được cấp phép**, không thể tự cho phép mọi user có authority cùng tên.

**Đừng coi "app-only" là "quản trị viên".** App-only chỉ mô tả actor là application. Dù client được cấp `reports.generate`, nó không có nghĩa được truy cập toàn bộ tài liệu mọi tenant hay làm mọi thao tác CRUD.

## 4. Ba lớp quyền: OAuth permission, app/user role, data permission

Trong thực tế, từ "permission" xuất hiện ở nhiều nơi:

1. **OAuth scope / application permission**: quyền trong access token hoặc trong authorization server/IdP.
2. **Ứng dụng nội bộ có role gì?** Ví dụ app `reporting-bot` được phép tạo report của tenant A; Alice có EDITOR trong tenant A.
3. **Ai được tác động lên chính object?** Ví dụ tài liệu 42 thuộc tenant A, owner Bob, share grant READ cho Alice.

Một công thức có thể dùng làm checklist:

```text
ALLOW delegated =
    validAccessTokenForThisAPI
    AND recognizedDelegatedUser
    AND clientAllowedForThisOperation
    AND tokenScopeAllowsAction
    AND userActiveAndTenantMembershipValid
    AND resourceTenantAndObjectPolicyAllows
    AND contextConditionsHold

ALLOW app-only =
    validAccessTokenForThisAPI
    AND recognizedAppIdentity
    AND appAssignedForThisOperation
    AND tokenPermissionAllowsAction
    AND appTenantAndResourceGrantAllows
    AND contextConditionsHold
```

Điểm khác nhau nằm ở vế **user entitlement** và **application entitlement**. Hai nhánh không được lén chuyển sang nhau khi thiếu dữ liệu.

Ví dụ Alice có `document:read` tại tenant B, nhưng token delegated chỉ có `reports.read`: Alice không thể dùng token đó đọc tài liệu qua endpoint yêu cầu `documents.read`. Ngược lại, token có `documents.read` nhưng Alice đã bị xóa khỏi tenant B thì quyền đọc B vẫn bị từ chối theo policy data. App-only có `documents.read` cũng chưa chắc được đọc document của tenant B nếu app grant chỉ giới hạn tenant A.

## 5. Luồng Authorization Code + PKCE: gọi API thay người dùng

Một ví dụ khái niệm:

```text
Alice                  Browser / Web Portal         Authorization Server
  |                            |                             |
  |--- Click "Sign in" ------->|                             |
  |                            |--- /authorize + PKCE ------>|
  |<------------ browser redirects / authentication -------->|
  |                            |<--- authorization code -----|
  |                            |--- code + verifier -------->|
  |                            |<--- delegated access token --|
  |                            |                             |
  |--- Read Doc42 ------------>|                             |
                               |--- Bearer delegated token --->
                                             Document API
                               <--- data allowed for Alice ---|
```

Authorization Code + PKCE là hướng phù hợp cho public clients/ứng dụng có user login; Confidential web clients cũng có thể dùng Authorization Code với client authentication và PKCE tùy cấu hình. Token được phép dùng ở resource server đã định trước (`aud`), không phải token có thể gửi tùy ý sang bất kỳ API.

**Điểm cốt lõi:** client có token do flow của Alice **không thể thay tên userId trong HTTP body** để trở thành Bob. Resource server phải lấy user subject từ token được xác minh hoặc từ delegation được xác thực, rồi đối chiếu với resource. Khi Alice logout hoặc quyền bị revoke, hệ thống phải xác định cách hết hiệu lực token/cache theo yêu cầu bảo mật.

### Delegated không đồng nghĩa browser luôn giữ token

Với BFF (Backend for Frontend), backend có thể giữ token thay browser và gọi API thay Alice. Bất kể token lưu ở đâu, nghiệp vụ vẫn phải biết **đúng subject Alice** được ủy quyền; không vì backend có service credential mà biến tất cả request user thành app-only superuser.

## 6. Luồng Client Credentials: ứng dụng tự gọi API

Một worker chạy định kỳ không cần user đăng nhập:

```text
Reporting Worker                  Authorization Server
      |                                    |
      |-- authenticate client ------------>|
      |   grant_type=client_credentials    |
      |   requested scope / resource       |
      |<-- app access token ---------------|
      |                                    |
      |---------- Bearer app token --------> Document API
      |                                     verify app identity, scope,
      |                                     tenant grant and action
      |<-------- report data / deny --------|
```

Ví dụ HTTP ở mức giao thức (các giá trị client credentials chỉ để minh họa, **không đặt secret trong URL hoặc code production**):

```http
POST /oauth2/token HTTP/1.1
Host: authorization.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=client_credentials&scope=reports.read
```

Authorization server xác thực chính client và cấp token theo cấu hình cho client đó. Token có thể dùng OAuth scopes, application roles hoặc provider-specific permissions. Nó **không phải** access token của một user chỉ vì app do một nhân viên sở hữu.

Với API nội bộ, service principal `reporting-bot` chỉ được các quyền như:

```text
client_id: reporting-bot
allowed tenants: tenant-a
allowed actions: READ_AGGREGATED_REPORTS
max data classification: INTERNAL
expires/requires service credential validation
```

Đó là **app assignment** do server tin cậy quản trị. Bất kỳ caller nào gửi header `X-User: alice` cùng app token cũng không trở thành Alice. Nếu một báo cáo cần xem dữ liệu mà chỉ Alice có quyền đọc, service phải có **delegated authorization được kiểm chứng** hoặc workflow approval phù hợp, không tự nâng quyền bằng app-only credential.

### Bẫy trong server có cả user request và client credentials

Một backend có thể vừa nhận request của Alice vừa cấu hình `OAuth2AuthorizedClientManager` lấy client-credentials token. Nếu một controller gọi downstream API bằng app-only token và đưa `userId` từ browser vào body, downstream chỉ biết app đã xác thực; muốn thực thi policy của Alice phải dùng một giao thức delegation được tin cậy, không dựa vào trường userId.

Một service credential rất mạnh trong backend tạo nguy cơ **confused deputy**: kẻ tấn công lợi dụng quyền của service thay vì quyền của chính mình. Cần đặt authorization trước khi backend phát sinh downstream call, hạn chế app grant và xác minh lại ở downstream theo policy.

## 7. Đừng suy luận loại token chỉ từ một claim tùy ý

OAuth2 không quy định một claim JWT duy nhất, tồn tại với mọi IdP, để phân biệt delegated và app-only. Những quan sát thường gặp:

| Tín hiệu | Nó có thể cho biết gì? | Vì sao không đủ một mình? |
| --- | --- | --- |
| `sub` | Subject được issuer gán | Trong client credentials, subject có thể chính là client |
| `client_id` / `azp` | Client được xác minh/authorized party | Có thể có trong cả user-delegated và app-only |
| `scope` / `scp` | Những scope token được cấp | Không chứng minh có user, không chứng minh owner |
| `roles` | Roles/app roles theo IdP schema | Có thể xuất hiện trong token user **hoặc** app tùy provider |
| `grant_type` / `gty` | Nếu issuer đưa vào, có thể liên hệ OAuth grant | Không bắt buộc có trong mọi access token |
| `iss` | Issuer token | Phải kiểm tra issuer trust trước khi tin claims |
| `aud` | Resource server/API nhận token | Không phải user/app role |
| `exp`, `nbf` | Thời hạn token | Không chứng minh grant object/ACL còn hiệu lực |

**RFC 9068** (JWT Profile for OAuth2 Access Tokens) mô tả rằng với grant có resource owner, `sub` **nên** là định danh resource owner; với grant không có resource owner như client credentials, `sub` **nên** là định danh client application. Từ "SHOULD" không phải hằng đẳng thức cho mọi issuer. `client_id` là claim bắt buộc trong profile đó, nhưng **không phải mọi access token đều tuân theo profile này**: access token có thể opaque và cần introspection.

Vì vậy, resource server phải dùng **hợp đồng token của issuer cụ thể** đã được tin cậy để phân loại caller. Một thiết kế có thể dùng:

- Token type/subject type được issuer bảo đảm và ký; hoặc
- Chính sách riêng theo authorization server, audience, issuer, client assignment; hoặc
- Token introspection trả metadata đủ tin cậy; hoặc
- Hai audiences/issuers hoặc hai loại token được cấu hình tách rõ.

**Không tin** một header `X-Actor-Type: USER`, một request body `{"kind":"delegated"}`, hoặc một JWT payload chưa verify để chuyển app principal thành user principal.

## 8. Hai access-token mẫu để hiểu claims

### 8.1. Delegated token mẫu

```json
{
  "iss": "https://idp.example.test/",
  "aud": "document-api",
  "sub": "user-alice",
  "client_id": "web-portal",
  "scope": "documents.read",
  "exp": 1800000000
}
```

Đây chỉ là **JWT claims minh họa**, không phải token thật/chữ ký. Với issuer theo profile JWT access-token, còn có yêu cầu `iat`, `jti` và header `typ`; ví dụ rút gọn ở đây để tập trung identity. Resource server phải xác thực đầy đủ theo issuer/profile trước khi sử dụng.

Nếu contract của issuer xác nhận đây là delegated user token, policy có thể gắn:

```text
USER(subjectId=user-alice, clientId=web-portal)
  has delegated scope documents.read
  AND is member of selected tenant
  AND can READ this Document by owner/ACL
```

### 8.2. App-only token mẫu

```json
{
  "iss": "https://idp.example.test/",
  "aud": "document-api",
  "sub": "reporting-bot",
  "client_id": "reporting-bot",
  "scope": "reports.read",
  "exp": 1800000000
}
```

Không có user Alice. Chính sách phải đánh giá:

```text
APPLICATION(clientId=reporting-bot)
  has app capability reports.read
  AND has approved access to selected tenant
  AND can READ the report data allowed to this service
```

**Không thể dùng `sub` của cả hai token như "userId" trong database.** Một token app-only có `sub=reporting-bot`; nếu hệ thống tìm bản ghi user cùng tên hoặc có owner ID trùng, có thể tạo quyền giả.

### Token validation là bước độc lập

Tối thiểu cần kiểm tra:

- Chữ ký, key/algorithm được phép, định dạng/profile token.
- Issuer `iss` được tin cậy.
- Audience `aud` đúng API.
- `exp`, `nbf` và clock skew hợp lý.
- Scope/permission hiện diện và được issuer cấp.
- Client authorization và caller kind theo issuer-specific contract.
- Nếu token opaque, introspection với Authorization Server đáng tin và caching/freshness rõ.

Không nhận **ID token** (dành cho OIDC client xác thực người dùng) làm OAuth2 API access token. ID token có audience thường là client ID, không phải resource server; dùng nhầm có thể tạo token-substitution vulnerability.

## 9. Scopes, roles, authorities: Spring Security nhìn thấy gì?

Spring Security OAuth2 Resource Server JWT mặc định thường đọc `scope` hoặc `scp` từ JWT được xác minh, chuyển thành `GrantedAuthority` có tiền tố `SCOPE_`.

Ví dụ:

```json
{
  "scope": "documents.read reports.read"
}
```

Có thể trở thành:

```text
SCOPE_documents.read
SCOPE_reports.read
```

Một expression:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public DocumentView readDocument(Long id) {
    // ...
}
```

chỉ kiểm tra authority **được gắn trên Authentication**. Nó **không có mặc định**:

- Xác minh đây là user token thay vì application token.
- Tính user business role từ tenant membership.
- Kiểm tra Document ID, owner, share grant và trạng thái.
- Đảm bảo client được phép thực hiện delegated action này.
- Tách role `ADMIN` trong tenant A khỏi tenant B.

Do đó không dùng `hasAuthority('SCOPE_documents.read')` làm bảo vệ duy nhất nếu API yêu cầu **user-specific data authorization**.

### Scope và application role không có mapping vạn năng

Ở một số IdP, app-only permissions xuất hiện trong claim `roles`; delegated permissions xuất hiện trong `scp`. **Microsoft Graph / Microsoft Entra** là ví dụ phổ biến về phân biệt delegated permissions và application permissions. Tuy nhiên **đây là quy ước của provider**, không phải phép xác định universally safe:

- Claim `roles` có thể chứa role của **user**, **application** hoặc domain mapping khác tùy issuer/API.
- Claim `scope` có thể có trong app-only token của authorization server khác.
- Có token không có JWT claims để xem trực tiếp (opaque token).
- Một token có claim trông giống app role chưa chắc đã được cấp đúng audience hoặc issuer.

**Bài học:** áp dụng quy tắc phân loại **được version hóa và kiểm chứng cho issuer/token profile cụ thể**. Không tự viết `if (has("roles")) APP else USER` làm chuẩn chung.

## 10. Mô hình caller có kiểu rõ ràng: USER khác APPLICATION

Một thiết kế Java 17 tốt có thể dùng sealed type để biểu diễn hai kiểu caller:

```java
public sealed interface VerifiedCaller
        permits DelegatedUserCaller, ApplicationCaller {

    String clientId();
    String tenantId();
}

public record DelegatedUserCaller(
    String userId,
    String clientId,
    String tenantId
) implements VerifiedCaller {}

public record ApplicationCaller(
    String clientId,
    String tenantId
) implements VerifiedCaller {}
```

Đây là **các type domain Java 17**; `tenantId` trong chúng phải xuất phát từ **tenant đã xác minh**, không gán từ request path chưa kiểm tra. `DelegatedUserCaller.userId` là user subject từ issuer đáng tin hoặc identity mapping nội bộ; `ApplicationCaller.clientId` là client đã được AS xác minh.

Việc dùng hai type tách biệt giúp policy không thể vô tình giả định mọi `Authentication.getName()` là user:

```java
switch (caller) {
    case DelegatedUserCaller user -> checkUserRead(user, document);
    case ApplicationCaller app -> checkAppRead(app, document);
}
```

**Chú ý Java 17:** switch pattern matching trên sealed types trong ví dụ này là **preview feature** ở Java 17 và không nên dùng như mã chạy mặc định khi chưa bật preview. Trong code sản xuất Java 17 không bật preview, dùng `if (caller instanceof DelegatedUserCaller user) ... else if (...)`, hoặc visitor rõ. Ví dụ chương trình runnable ở cuối dùng `instanceof` để chạy `javac`/`java` thông thường không cần `--enable-preview`.

### Interface token classifier có hợp đồng riêng

```java
public interface VerifiedCallerResolver {
    VerifiedCaller resolve(
        org.springframework.security.core.Authentication authentication,
        String requestedTenantId
    );
}
```

Một implementation an toàn phải:

1. Nhận `Authentication` đã qua Resource Server validation.
2. Xác định issuer/token profile đã được cấu hình.
3. Phân loại user/app bằng **metadata đáng tin theo issuer**, không đoán từ tên claim.
4. Kiểm tra client ID thuộc registry/assignment được chấp nhận.
5. Với user: map subject vào user identity, verify tenant membership.
6. Với app: verify client assignment trong tenant và scope mục đích.
7. Từ chối token không phân loại được hoặc thiếu required claims.
8. Không trả "default admin" khi thông tin không đầy đủ.

**Không có một `VerifiedCallerResolver` built-in chung của Spring Security** làm toàn bộ các bước trên cho mọi IdP. Đây là abstraction do ứng dụng sở hữu.

## 11. Quyền delegated hiệu quả là phép giao, không phải phép hợp

Giả sử Alice có:

```text
Alice in tenant-a:
  user permissions = {documents.read, documents.edit}

Web Portal token for Alice:
  token scopes = {documents.read}

Document42:
  tenant = tenant-a
  owner = alice

Document43:
  tenant = tenant-a
  owner = bob
  no share for alice
```

Kết quả:

| Request | Token scope | User/domain permission | Kết quả |
| --- | --- | --- | --- |
| Alice đọc Document42 | Có documents.read | Có owner READ | ALLOW |
| Alice sửa Document42 | **Không** documents.edit | User có EDIT nhưng token thiếu scope | DENY |
| Alice đọc Document43 | Có documents.read | Không owner/share | DENY |
| Alice đổi tenant sang B | Có documents.read | Không membership B | DENY |
| Bob dùng token Alice để gọi API | Token vẫn mang Alice subject | Hệ thống coi caller theo token Alice, đây là token theft | Phải bảo vệ token; không đọc tên Bob từ request |

Thông thường:

```text
effective delegated permission
    ⊆ token scopes granted to client
    ∩ resource owner's current business rights
    ∩ resource/tenant policy
    ∩ contextual constraints
```

Ký hiệu ở đây mang ý nghĩa giao các điều kiện, không phải phép giao tập hợp theo nghĩa mọi hệ thống có cùng taxonomy permissions.

### Consent không cấp mọi quyền dữ liệu

User/admin consent cho `documents.read` chỉ nói ứng dụng được xin quyền đọc theo phạm vi cấp phép. Nó không tự biến mọi dữ liệu của tenant thành public với client. Resource server vẫn chịu trách nhiệm kiểm tra ACL/owner/tenant và áp dụng field-level restrictions.

Nếu một consent là delegated, quyền thực thi có thể bị giới hạn bởi **quyền của user**. Nếu là application permission, giới hạn là **app assignment** và policy API. Cần phân biệt cả hai, không chỉ label trong portal quản trị IdP.

## 12. Quyền ứng dụng: app principal cần grant và dữ liệu riêng

Giả sử app `invoice-sync` được cấp quyền đọc hóa đơn trong tenant A:

```text
service/application identity: invoice-sync
tenant assignment: tenant-a
allowed API action: invoices.read
allowed resource domain: invoices tagged for ERP sync
max classification: INTERNAL
approval: integration-admin
```

Khi gọi:

```http
GET /api/tenants/tenant-a/invoices/991
Authorization: Bearer <invoice-sync-app-token>
```

API cần kiểm tra:

1. Token được xác minh, issuer/audience và app identity hợp lệ.
2. App có assignment cho tenant A.
3. App được cấp action `invoices.read`.
4. Invoice 991 thuộc tenant A và được đánh dấu có thể đồng bộ ERP.
5. Invoice chưa bị xóa/khóa theo policy.
6. Dữ liệu trả về chỉ gồm trường được phép cho integration.

Không vì app token có scope `invoices.read` mà bỏ qua giới hạn "chỉ hóa đơn được đồng bộ". Ứng dụng có thể được phép đọc **dữ liệu mà user thường không được phép**, nhưng đó phải là một **app-specific business policy được phê duyệt**, không phải mặc định bypass.

### Service account không phải user giả

Một hệ thống có thể lưu service account trong bảng chung với user, nhưng **kiểu chủ thể phải tách được**. Tránh dùng `serviceAccount.email` để suy ra user owner hoặc đưa service vào nhóm `ROLE_USER` vô điều kiện. Nếu cần app có vai trò quản trị nội bộ, biểu diễn bằng service principal, assignment, audit và hạn chế action rõ.

Một admin toàn cục cũng nên được cấp qua explicit policy riêng; client credentials không phải căn cứ tự động để cấp `ROLE_ADMIN`.

## 13. Confused deputy: khi backend dùng app token để làm việc thay user

Đây là lỗi đáng chú ý nhất khi phân biệt hai loại quyền.

### Lưu đồ sai

```text
Alice có quyền đọc Doc10, không có quyền đọc Doc99
             |
             v
Frontend gửi /documents/99?userId=alice
             |
             v
Backend dùng client_credentials token có documents.read.all
             |
             v
Document API chỉ thấy APP/BACKEND có quyền rộng
             |
             v
Trả Doc99 dù Alice không có quyền
```

Khi đó backend trở thành **deputy có quyền mạnh**, thực hiện yêu cầu không hợp lệ của Alice. Nếu không có bước kiểm tra policy user, API phía sau không thể suy ra rằng "Alice yêu cầu" một cách đáng tin từ token app-only.

### Hướng sửa 1: token delegated từ đúng OAuth flow

```text
Alice -> BFF (session/user authenticated)
      -> obtains valid delegated access token for Document API
      -> Document API verifies Alice + client + scopes
      -> checks Alice tenant/owner/ACL for Doc99 -> DENY
```

Không phải mọi kiến trúc hoặc IdP đều cho phép chuyển token từ browser sang backend. BFF phải dùng OAuth flow được hỗ trợ để lấy đúng access token cho API, bảo vệ token và CSRF/session khi phù hợp.

### Hướng sửa 2: explicit trusted delegation / token exchange

Đôi khi backend dùng token exchange/on-behalf-of:

```text
User token for intermediary
  -> trusted STS / authorization server
  -> delegated downstream token, correct audience
  -> downstream validates actor/user/client/delegation constraints
```

OAuth2 Token Exchange (RFC 8693) cung cấp framework chuyển token với `subject_token` và `actor_token` theo contract. Nhưng **không phải IdP nào cũng hỗ trợ đầy đủ**, và không thể tự đổi token bằng cách copy claim `sub` vào JWT mới do app tự ký.

Downstream phải tin **authorization server có thẩm quyền** đối với delegation chain, scope/actor và audience; tuyệt đối không tin request header tự khai "on behalf of Alice".

### Hướng sửa 3: backend app-only + domain authorization rõ

Có workflow mà backend thực sự cần app credential nhưng phải chịu trách nhiệm kiểm tra quyền của user ở front boundary:

```text
User authenticated at gateway
 -> gateway/service checks user can initiate action on resource
 -> creates narrow, audited command with verified user + resource
 -> app service authenticates command producer
 -> rechecks command scope and app grant
 -> acts only within approved resource/action
```

Với những thao tác nhạy cảm như DELETE, EXPORT, SHARE, backend nên recheck hoặc sử dụng signed authorization context với expiry/replay protection, transaction policy và audit tùy threat model. Không xem một string `initiatedBy` trong message queue là proof.

## 14. Access token không nên được dùng thay ID token

**OIDC ID token** chủ yếu phục vụ việc client biết user đã được xác thực theo OpenID Connect. **OAuth2 access token** dùng để gọi resource server/API.

| Token | Audience chính | Mục tiêu |
| --- | --- | --- |
| ID token | OIDC client | Xác thực danh tính user cho client |
| OAuth access token | Resource server/API | Gọi API trong scope được cấp |
| Refresh token | Authorization server | Xin token mới trong điều kiện chính sách cho phép |

Một API chấp nhận ID token chỉ vì nó có `sub=alice` có thể bị token substitution: token có audience/semantics không dành cho API lại được hiểu là permission. Resource server phải yêu cầu **access token đúng audience và token profile**, không dùng ID token như bearer API credential.

Một token `client_credentials` thường không cần refresh token; service có thể xác thực lại client để lấy access token mới. Tuy nhiên hãy dựa vào authorization server và API behavior thực tế thay vì hardcode suy luận từ một grant_type string trên token.

## 15. Spring Security Resource Server JWT: xác thực trước, phân loại sau

Spring Boot Resource Server cấu hình bằng dependency Resource Server + JOSE JWT và issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/
          audiences: document-api
```

Đây là **cấu hình ví dụ**, `example.test` không phải IdP thật. Thuộc tính audiences có trong các cấu hình Spring Boot/Spring Security hiện hành; tùy phiên bản cần custom `OAuth2TokenValidator<Jwt>`. Không đưa token từ issuer lạ vào runtime chỉ vì URL issuer nằm trong một JWT chưa verify.

### Một SecurityFilterChain cho API

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Đây là **Servlet Spring Security configuration fragment**. Nó cần Spring MVC/Servlet application, JWT decoder/issuer/audience config và endpoint thật. CSRF/CORS, session strategy, security headers và exception handling cần thiết kế theo loại client: nếu API cookie-based hoặc browser session, đừng sao chép cách disable CSRF thường dùng cho pure bearer-only APIs.

Lưu ý: `authenticated()` chỉ xác nhận có Authentication hợp lệ. Nó **không phân biệt** user-app type hay bảo vệ object. Bảo vệ cả hai nằm ở application policy/service hoặc custom authorization managers.

### Spring Boot đang chạy WebFlux?

Nếu ứng dụng reactive, dùng `ServerHttpSecurity` + `SecurityWebFilterChain` và `@EnableReactiveMethodSecurity`, không copy class Servlet này như cấu hình hoạt động tương đương. Ý nghĩa security giống nhau, API khác. Bài tập trung vào quyền OAuth, không xem hai stack là một.

## 16. JwtAuthenticationConverter và scope mapping

Với JWT access tokens, Spring Security mặc định thường tạo `JwtAuthenticationToken` và chuyển `scope`/`scp` thành `SCOPE_*`.

Ví dụ tùy chỉnh tên claim khi issuer dùng một claim khác:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public JwtAuthenticationConverter scopeConverter() {
    JwtGrantedAuthoritiesConverter grants =
        new JwtGrantedAuthoritiesConverter();
    grants.setAuthoritiesClaimName("scope");
    grants.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grants);
    return converter;
}
```

Đây là **method fragment**. Nếu register bean và gắn vào `oauth2ResourceServer(...).jwt(jwt -> jwt.jwtAuthenticationConverter(...))`, nó đổi authority conversion. Không mặc định `roles` biến thành `ROLE_*` hoặc roles thuộc USER; mapping là **issuer-specific**, cần test cả app-only và delegated.

Một đoạn code kiểu:

```java
if (authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("SCOPE_documents.read"))) {
    return true;
}
```

là **không đủ** để cấp quyền đọc dữ liệu người dùng. Cả app-only và delegated token có thể chứa authority đó tùy issuer; cần phân biệt caller kind và kiểm tra data.

### Đừng tự nối mọi "role" thành ROLE_ADMIN

Một custom converter có thể lấy roles từ JWT rồi tạo `ROLE_ADMIN`. Nếu app-only token có một app role `Admin` theo provider, mapper không được tự hiểu đó là **quyền admin của người dùng** trong domain. Cần namespace:

```text
token scope:        SCOPE_documents.read
trusted app grant:  APP_REPORT_EXPORT
trusted user role:  TENANT_A_EDITOR (khi membership được xác minh)
```

Các chuỗi trên là **quy ước nội bộ minh họa**, không phải authority chuẩn do Spring tự tạo. Tên `ROLE_` có ý nghĩa đối với `hasRole(...)`; đừng làm cùng một role string có hai nghĩa đối với USER và APPLICATION.

## 17. Phân loại caller trong Spring: contract phải đến từ issuer

Một ví dụ ứng dụng có thể định nghĩa claim riêng `actor_kind` được authorization server nội bộ **ký và bảo đảm** nhận một trong `delegated_user` hoặc `application`. Đây không phải claim OAuth2 tiêu chuẩn; chỉ dùng khi **IdP của bạn đã phát hành đúng như vậy**.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public final class TrustedActorClassifier {
    public VerifiedCaller classify(
            JwtAuthenticationToken authentication,
            String verifiedTenantId) {

        Jwt jwt = authentication.getToken();
        String kind = jwt.getClaimAsString("actor_kind");
        String client = jwt.getClaimAsString("client_id");

        if (client == null || client.isBlank()) {
            throw new AccessDeniedException("Unknown OAuth client");
        }

        // Các call này cần dùng trusted registry/tenant grant trong app.
        if ("delegated_user".equals(kind)) {
            String userSubject = jwt.getSubject();
            if (userSubject == null || userSubject.isBlank()) {
                throw new AccessDeniedException("Missing user identity");
            }
            return new DelegatedUserCaller(
                userSubject, client, verifiedTenantId);
        }

        if ("application".equals(kind)) {
            return new ApplicationCaller(client, verifiedTenantId);
        }

        throw new AccessDeniedException("Unrecognized actor kind");
    }
}
```

Đây là **class component minh họa**, sử dụng `VerifiedCaller`/record ở phần trước. `verifiedTenantId` phải được xác minh **trước khi gọi**, ví dụ bằng server-side membership/client assignment; không được đi thẳng từ `@PathVariable tenantId`. Class mới phân loại actor, **chưa cấp một permission nào**. Chính sách bên dưới phải truy membership/grant.

Một triển khai production cần kiểm tra:

- JwtAuthenticationToken thực sự do decoder tin cậy tạo và token profile phù hợp.
- Issuer và audience đã được validate theo contract.
- Client có được phép trong registry của hệ thống.
- Claim `actor_kind` do issuer quản lý, không phải field do client tự khai trong request.
- Với delegated: user identity và client consent hợp lệ.
- Với app: app assignment và permission được quản trị.
- Nếu issuer không cung cấp claim này: **không đoán**, mà triển khai issuer-specific classifier khác.

**Không dùng class này trực tiếp với Entra/Keycloak/Okta nếu họ không phát claim `actor_kind` đúng hợp đồng.** Đây là abstraction gợi ý để giảm nhầm lẫn giữa actor, không phải thư viện Spring Security mặc định.

## 18. Domain policy: hai nhánh quyết định tách biệt

Một service ứng dụng có thể định nghĩa:

```java
public boolean canRead(
        VerifiedCaller caller,
        DocumentFacts resource,
        Set<String> tokenScopes) {

    if (caller == null || resource == null
            || !tokenScopes.contains("documents.read")
            || resource.deleted()) {
        return false;
    }

    if (!caller.tenantId().equals(resource.tenantId())) {
        return false;
    }

    if (caller instanceof DelegatedUserCaller user) {
        return users.isActiveMember(
                   user.userId(), user.tenantId())
            && (
                user.userId().equals(resource.ownerId())
                || shares.hasActiveGrant(
                    user.userId(), resource.id(), "READ")
            );
    }

    if (caller instanceof ApplicationCaller app) {
        return appAssignments.canRead(
            app.clientId(), app.tenantId(), resource.id());
    }

    return false;
}
```

Đây là **pseudocode Java-style fragment**: `DocumentFacts`, `users`, `shares` và `appAssignments` là domain objects/services; cần đưa vào service class, dependency injection, transaction/context và cache invalidation. `tokenScopes` phải lấy từ verified token hoặc authorization context, không phải client JSON.

Tính chất quan trọng:

1. Shared conditions: đúng tenant, resource active, đúng action/scope.
2. User branch: **active membership + owner/ACL**.
3. App branch: **approved app assignment + resource scope**.
4. Không có đường **app → mặc định user**.
5. Unknown caller → DENY.
6. Business role của user và application privilege không gộp thành một `ROLE_ADMIN`.

### Phòng tránh TOCTOU

Nếu check `canRead` xong rồi handler truy `documents.findById(id)` không scope, một race hoặc đường gọi khác có thể làm lộ dữ liệu. Với truy vấn quan trọng, dùng:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND deleted = FALSE;
```

Với delegated USER, cần thêm owner/ACL/share predicates; với app-only, thêm app assignment/resource grant theo domain. Nếu update/delete, dùng conditional SQL hoặc transaction/lock phù hợp, không chỉ hậu kiểm sau khi ghi.

**Không** để batch service app-only gọi một repository method `findAll()` rộng rồi tự filter theo userId header.

## 19. OAuth2 Client trong Spring: xin token app-only đúng mục đích

Một Spring Boot service cần gọi downstream API bằng client credentials có thể đăng ký client riêng:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-client:
            provider: reports-idp
            client-id: reporting-bot
            client-secret: \${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reports-idp:
            token-uri: https://idp.example.test/oauth2/token
```

Đây là **configuration ví dụ**, không phải credentials thật. Trong file YAML thực, truyền secret qua secret manager/environment, tránh commit plaintext. Chuỗi `\${REPORTS_CLIENT_SECRET}` là placeholder cấu hình Spring ở runtime, không phải một việc còn thiếu trong nội dung bài.

### AuthorizedClientServiceOAuth2AuthorizedClientManager

Đối với **Servlet/unattended service** sử dụng Spring Security OAuth2 Client, có thể tạo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportingClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager appClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

Đây là **Spring configuration class**; cần dependency Spring Security OAuth2 Client, registration/provider thật, cấu hình secure store và lifecycle. Với WebFlux có **ReactiveOAuth2AuthorizedClientManager** và service-reactive counterpart, không thay Servlet manager này bằng việc `block()` trong event loop.

Xin token theo registration:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public String fetchAppToken(OAuth2AuthorizedClientManager manager) {
    OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("reports-client")
            .principal("reporting-service")
            .build();

    OAuth2AuthorizedClient authorized =
        manager.authorize(request);

    if (authorized == null) {
        throw new IllegalStateException(
            "No authorized client for reports-client");
    }

    return authorized.getAccessToken().getTokenValue();
}
```

Đây là **method fragment** (không phải standalone class) minh họa cơ chế; lưu ý không nên log/serialize token string. `principal("reporting-service")` là **key quản lý OAuth2AuthorizedClient cho service application**, **không tạo ra user Reporting Service ở resource server**. Nếu ứng dụng dùng client credentials, token vẫn đại diện client đã được authorization server xác thực.

### Điểm dễ nhầm về caching và principal

Một ứng dụng Web có nhiều user có thể dùng `OAuth2AuthorizedClientManager` để quản lý **authorized clients theo user session/principal**, nhưng với job nền app-only token lại thường có key service riêng. Không dùng key principal của Alice trong client credentials rồi suy luận access token đã trở thành delegated token của Alice.

Một báo cáo được yêu cầu bởi Alice có thể cần lưu **initiator metadata** cho audit và authorization ở tầng nghiệp vụ. Nhưng identity của access token dùng downstream vẫn là **application** nếu grant thực sự là client credentials.

## 20. JWT converter không nên tự gộp quyền app và user

Đôi khi issuer có claim `roles` cho app-only và delegated; ta muốn tùy chỉnh:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

JwtGrantedAuthoritiesConverter roles =
    new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
```

Đây là **converter fragment**, không tự cấu hình đầy đủ. Mối nguy không nằm ở việc đọc claims, mà ở **giải thích sai scope/role**:

- `ROLE_ADMIN` từ app grant không tự là USER global ADMIN.
- `ROLE_EDITOR` từ user token chưa chắc áp toàn bộ tenants.
- `SCOPE_documents.read` không chứng minh permission owner/ACL.
- Thay authority prefix không chuyển đổi bản chất của token.

Một thiết kế rõ hơn là tạo policy methods phân biệt `VerifiedCaller`, sau đó kiểm tra **token scope** và **domain grant riêng**. Nếu cần canonical authorities, namespace quyền app và delegated một cách nhất quán theo issuer type, với unit tests ngăn principal-kind escalation.

## 21. Java 17 chạy độc lập: cùng scope, hai nguồn quyền khác nhau

Ví dụ sau **không cần Spring Security hoặc OAuth library**. Nó giả lập các actor đã được xác minh bởi authorization server/Resource Server, sau đó mô phỏng policy. Mục tiêu là chứng minh **cùng `documents.read` không cho cùng quyền dữ liệu**: USER phải có membership/owner; APPLICATION phải có app assignment trên resource.

Lưu file `OAuthActorPermissionDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class OAuthActorPermissionDemo {

    sealed interface Actor permits UserActor, AppActor {
        String tenantId();
        Set<String> scopes();
    }

    record UserActor(
        String userId,
        String clientId,
        String tenantId,
        Set<String> scopes
    ) implements Actor {}

    record AppActor(
        String clientId,
        String tenantId,
        Set<String> scopes
    ) implements Actor {}

    record Document(
        long id, String tenantId, String ownerId, boolean deleted
    ) {}

    static final Map<String, Boolean> MEMBERSHIPS = Map.of(
        "alice|tenant-a", true,
        "bob|tenant-a", true,
        "alice|tenant-b", false
    );

    static final Map<String, Set<Long>> APP_GRANTS = Map.of(
        "reporting-bot|tenant-a", Set.of(11L)
    );

    static final Document A10 =
        new Document(10, "tenant-a", "alice", false);
    static final Document A11 =
        new Document(11, "tenant-a", "bob", false);
    static final Document B20 =
        new Document(20, "tenant-b", "carol", false);

    static boolean readAllowed(Actor actor, Document doc) {
        if (actor == null || doc == null || doc.deleted()
                || !actor.scopes().contains("documents.read")
                || !actor.tenantId().equals(doc.tenantId())) {
            return false;
        }

        if (actor instanceof UserActor user) {
            boolean member = MEMBERSHIPS.getOrDefault(
                user.userId() + "|" + user.tenantId(), false);
            return member && user.userId().equals(doc.ownerId());
        }

        if (actor instanceof AppActor app) {
            Set<Long> permitted = APP_GRANTS.getOrDefault(
                app.clientId() + "|" + app.tenantId(), Set.of());
            return permitted.contains(doc.id());
        }

        return false;
    }

    static boolean canRunReport(Actor actor) {
        return actor instanceof AppActor app
            && app.clientId().equals("reporting-bot")
            && app.scopes().contains("reports.generate");
    }

    static boolean canReadOwnProfile(Actor actor) {
        return actor instanceof UserActor user
            && MEMBERSHIPS.getOrDefault(
                user.userId() + "|" + user.tenantId(), false);
    }

    static String label(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        UserActor alice = new UserActor(
            "alice", "web-portal", "tenant-a",
            Set.of("documents.read"));
        UserActor bob = new UserActor(
            "bob", "web-portal", "tenant-a",
            Set.of("documents.read"));
        UserActor revoked = new UserActor(
            "alice", "web-portal", "tenant-b",
            Set.of("documents.read"));
        UserActor noScope = new UserActor(
            "alice", "web-portal", "tenant-a",
            Set.of("reports.read"));

        AppActor reporting = new AppActor(
            "reporting-bot", "tenant-a",
            Set.of("documents.read", "reports.generate"));
        AppActor wrongTenant = new AppActor(
            "reporting-bot", "tenant-b",
            Set.of("documents.read", "reports.generate"));
        AppActor unknown = new AppActor(
            "unknown-app", "tenant-a",
            Set.of("documents.read"));

        System.out.println("Alice own A10: "
            + label(readAllowed(alice, A10)));
        System.out.println("Alice Bob A11: "
            + label(readAllowed(alice, A11)));
        System.out.println("Bob own A11: "
            + label(readAllowed(bob, A11)));
        System.out.println("Reporting app A11 grant: "
            + label(readAllowed(reporting, A11)));
        System.out.println("Reporting app A10 not granted: "
            + label(readAllowed(reporting, A10)));
        System.out.println("Reporting app tenant B: "
            + label(readAllowed(wrongTenant, B20)));
        System.out.println("Unknown app A11: "
            + label(readAllowed(unknown, A11)));
        System.out.println("Alice missing scope: "
            + label(readAllowed(noScope, A10)));
        System.out.println("Alice revoked tenant B: "
            + label(readAllowed(revoked, B20)));
        System.out.println("App report action: "
            + label(canRunReport(reporting)));
        System.out.println("User report action: "
            + label(canRunReport(alice)));
        System.out.println("User profile action: "
            + label(canReadOwnProfile(alice)));
        System.out.println("App profile action: "
            + label(canReadOwnProfile(reporting)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac OAuthActorPermissionDemo.java
java OAuthActorPermissionDemo
```

Stdout chính xác:

```text
Alice own A10: ALLOW
Alice Bob A11: DENY
Bob own A11: ALLOW
Reporting app A11 grant: ALLOW
Reporting app A10 not granted: DENY
Reporting app tenant B: DENY
Unknown app A11: DENY
Alice missing scope: DENY
Alice revoked tenant B: DENY
App report action: ALLOW
User report action: DENY
User profile action: ALLOW
App profile action: DENY
```

**Giải thích:**

- Alice là user, có scope READ nhưng không thể đọc tài liệu Bob A11 chỉ vì cùng tenant.
- Bob có owner entitlement với A11 nên READ được.
- Reporting bot là **application**, có explicit app grant chỉ cho A11. Nó không thể đọc A10 dù Alice sở hữu A10 và A10 cùng tenant.
- Reporting bot không có grant ở tenant B, không được "đọc tất cả" vì có app token.
- Unknown app có cùng scope nhưng không có assignment → DENY.
- Alice thiếu scope trong token hoặc membership B đã bị revoke → DENY.
- `canRunReport` chỉ nhận application có identity/scopes cần thiết; user không được tự gọi job service-only.
- `canReadOwnProfile` chỉ nhận user đã có membership; app-only không có profile người dùng để tự đọc.

**Giới hạn:** các actor được tạo sẵn trong Java chứ không lấy từ JWT đã verify. `APP_GRANTS`/`MEMBERSHIPS` chỉ là dữ liệu in-memory, không có database, TTL, revoke event, transaction hay concurrency; ứng dụng thật phải nhận actor từ token contract và hệ thống phân quyền tin cậy. Demo minh họa policy phân loại actor, **không phải một OAuth authorization server hoặc resource server thực tế**.

## 22. Thiết kế API riêng cho user và app

Không phải lúc nào nên dùng chung một endpoint cho hai loại caller.

### Endpoint chỉ dành cho user

```http
GET /api/me/documents
Authorization: Bearer <delegated-user-token>
```

Ở đây `/me` nghĩa là **user được chứng minh trong token**, không phải "người sở hữu client". Nếu app-only token gọi, trả lỗi không có user context (thường 403 khi token đã authenticated nhưng actor sai). Đừng fallback sang `service-owner@example.test` hoặc `system`.

### Endpoint chỉ dành cho app/service

```http
POST /api/internal/reports/rebuild
Authorization: Bearer <client-credentials-token>
Content-Type: application/json

{"tenantId":"tenant-a","reportId":"quarterly"}
```

Chỉ ứng dụng đã được assign action/tenant tương ứng mới được gọi, với audit riêng. `tenantId` trong body chỉ là selector: kiểm tra service app assignment trước khi tạo job. Endpoint nên còn có rate limit, idempotency, approval và network/service authentication phù hợp.

### Endpoint chấp nhận cả hai

Một endpoint `GET /api/documents/{id}` có thể phục vụ delegated user và app-only nếu domain yêu cầu. Khi đó policy phải là OR **giữa hai nhánh đã hoàn chỉnh**, không OR giữa hai authority chung:

```text
ALLOW =
    sharedMandatoryChecks
    AND
    (
      verifiedDelegatedUser AND userResourcePolicyAllows
      OR
      verifiedApplication AND appResourcePolicyAllows
    )
```

Đừng viết `hasAuthority("SCOPE_documents.read") OR isAdmin()` nếu `isAdmin()` có thể được suy ra từ app role không đúng phạm vi. Các mandatory checks như tenant, resource state, token audience phải áp cho **mọi** nhánh.

## 23. On-behalf-of, token exchange và actor chains

Trong microservices, Alice → Service A → Service B → Document API có thể tạo nhiều lớp identity:

```text
originating user: Alice
immediate caller: Service B
OAuth client at current hop: Service B
requested action: READ Document 42
delegation chain: Alice -> Service A -> Service B
resource: Document 42 in tenant A
```

Không nên mất user identity hoặc không ghi service actor:

- Nếu B nhận app-only token từ A nhưng không có delegation proof, B chỉ biết app identity đã xác thực.
- Nếu B nhận token exchange có `act`/actor metadata theo issuer contract, B có thể phân biệt **subject** và **actor**.
- Nếu B nhận user token Alice nhưng token đó có `aud=service-a`, B **không nên** chấp nhận nó cho `aud=service-b` chỉ vì chữ ký hợp lệ.
- Nếu B cần gọi C, cần access token cho **đúng audience C** theo flow được AS hỗ trợ.

**RFC 8693** mô tả token exchange nhưng không có nghĩa mọi authorization server phải phát `act` cùng semantic giống nhau. Resource server phải validate token format và delegation context theo profile đã thống nhất.

Một audit record giàu thông tin:

```json
{
  "requestId": "r-123",
  "callerKind": "DELEGATED_USER",
  "userId": "alice",
  "clientId": "document-frontend",
  "actingService": "backend-gateway",
  "tenantId": "tenant-a",
  "resourceType": "Document",
  "resourceId": "42",
  "action": "READ",
  "decision": "DENY",
  "reasonCode": "NO_RESOURCE_GRANT"
}
```

Đây là **record minh họa**. Log phải bảo vệ privacy, không chứa raw access token, client secret, profile nhạy cảm hoặc payload tài liệu. Với app-only, `userId` nên **không có**, trừ khi một initiator đã được chứng minh và được lưu riêng, không dùng nó làm principal của token.

## 24. Quyền app và quyền user trong hệ thống nhiều tenant

Một user có thể là ADMIN ở tenant A và VIEWER ở tenant B. Một app có thể được assign chỉ trong tenant A. Đây là **hai dimension độc lập**.

| Caller | Tenant | Quyền nguồn | Đọc Document A10 | Đọc Document B20 |
| --- | --- | --- | --- | --- |
| Alice delegated | A | User EDITOR, token READ | Theo owner/ACL A | Không được do khác tenant |
| Alice delegated | B | User VIEWER, token READ | Không được do khác tenant | Theo owner/ACL B |
| Reporting bot app-only | A | App assignment REPORTS_READ | Chỉ data được cấp cho app trong A | Không |
| Reporting bot app-only | B | Không có assignment | Không | Không |
| Admin trong A | B | Không có admin B | Không vượt tenant | Theo role B nếu có |

**Không dùng JWT authority toàn cục** `ROLE_ADMIN` vì user có admin tại A rồi cho quyền ADMIN tại B. Cũng không dùng app-only authority `ROLE_ADMIN` để cho app sửa mọi tenant.

Với owner/resource object, query nên có `tenant_id = :verifiedTenant`, data permission theo branch. Nếu dữ liệu thật bị cache, key phải có caller type + user ID hoặc client ID + tenant + resource + action + policy/ACL version. Một cached ALLOW của Alice không được áp cho bot, và ALLOW của bot không được dùng cho Alice.

### Membership và app assignment có thể bị thu hồi

Khi admin revoke Alice khỏi B, token delegated còn hạn có thể vẫn xác thực chữ ký. Khi revoke app reporting-bot, token app-only còn hạn cũng vậy. Resource server cần kiểm tra current entitlements hoặc cơ chế revocation/introspection/version/short TTL với SLA rõ. Không chỉ "xóa nút ở UI" là đủ.

## 25. Quyền ứng dụng ở Microsoft Graph là ví dụ, không phải chuẩn toàn OAuth

Microsoft Graph phân biệt:

- **Delegated permissions**: ứng dụng gọi Graph thay mặt user đã đăng nhập. Effective privileges bị giới hạn bởi **cả scopes của app và quyền của user**.
- **Application permissions**: ứng dụng gọi Graph bằng danh tính chính nó mà không cần user. Những quyền này có thể rất rộng và thường cần cơ chế quản trị/consent phù hợp.

Trong access token Microsoft identity platform/Graph, `scp` thường thể hiện delegated scopes; `roles` thường thể hiện application permissions trong app-only token. Tuy nhiên, các **user app roles** cũng có thể sử dụng `roles` theo từng ứng dụng/issuer. Không viết logic **mọi JWT có roles đều là app-only**.

Các hệ thống khác có thể phát `scope` cho client credentials, `permissions` ở claim riêng hoặc opaque token. Phải tham khảo **token claim mapping của chính IdP** và audience/resource server đang dùng.

### Consent không thay object authorization

Một app được admin consent Graph application permission rộng có thể thực hiện nhiều hành động mà user thường không được phép. Đó là lý do phải cẩn thận với service credentials; Graph có cơ chế và quyền riêng, còn API nội bộ phải tự triển khai app assignment/tenant scope thích hợp. Đừng bê tên permission như `Files.Read.All` từ Graph sang endpoint tài liệu nội bộ rồi coi chúng có cùng semantics.

## 26. Kiểm thử Spring Security thực tế

### 26.1. Unit tests cho caller classification

Tạo fixtures cho các tình huống:

- Token delegated với user subject Alice và client web-portal.
- Token app-only với client reporting-bot, **không có user**.
- Token có `scope=documents.read` giống nhau ở hai kind.
- Token từ issuer không được tin cậy.
- Token thiếu/unknown `actor_kind` theo custom contract.
- Token user có `client_id` hợp lệ nhưng tenant membership bị revoke.
- Token app có `roles` nhưng không có app grant cho resource.
- ID token và access token sai audience.
- Token ký đúng nhưng đã hết hạn.
- Resource khác tenant, owner khác người hoặc grant hết hạn.

Một assert quan trọng: `classify(app-only)` **không bao giờ** tạo `DelegatedUserCaller` chỉ vì request body có `userId=alice`.

### 26.2. MockMvc với mockJwt()

`spring-security-test` hỗ trợ `SecurityMockMvcRequestPostProcessors.jwt()`. Ví dụ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/me/documents")
        .with(jwt()
            .jwt(j -> j.subject("user-alice")
                .claim("actor_kind", "delegated_user")
                .claim("client_id", "web-portal"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isOk());
```

**Fragment:** cần Spring Boot/Test context, security configuration, controller/fixtures, proper Principal/tenant membership. 200 chỉ đúng khi response handler tồn tại và user được cấp quyền; không dùng một test đơn lẻ để chứng minh đúng policy. Với app-only fixture:

```java
mockMvc.perform(get("/api/me/documents")
        .with(jwt()
            .jwt(j -> j.subject("reporting-bot")
                .claim("actor_kind", "application")
                .claim("client_id", "reporting-bot"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isForbidden());
```

Đây cũng là **fragment**, kỳ vọng 403 dựa trên API contract user-only. **Điểm trọng yếu:** app có cùng scope với user nhưng vẫn bị từ chối bởi caller-kind policy. Nếu chưa cấu hình actor classifier/authorization đúng, test không thể tự PASS.

`mockJwt()` **không xác minh JWT signature/issuer/audience thực**: nó mô phỏng Authentication cho authorization test. Bổ sung integration test với resource server decoder và token từ issuer kiểm thử để xác nhận parsing/validation/token-type contract.

### 26.3. Test client credentials và call chain

Có thể dùng mock HTTP token endpoint hoặc IdP test environment để xác nhận:

1. Spring OAuth2 Client dùng `authorization-grant-type=client_credentials`.
2. Token nhận được là cho chính **client reporting-bot**, không có delegated user.
3. Token được gọi tới **đúng audience** downstream API.
4. Resource server từ chối app không có tenant/resource grant.
5. User request với forged `X-User-Id` không thể tăng quyền của bot.
6. BFF với user token không đổi thành app-only khi truyền qua các service.
7. Service chỉ được phép dùng app credential ở route/workflow được phê duyệt.
8. Khi app grant revoked, cache/policy áp dụng đúng SLA.
9. Credential rotation làm service tiếp tục hoạt động mà không leak secrets.
10. Các job async lưu actor kind và audit rõ ràng.

## 27. Ma trận kiểm thử quyền đầy đủ

| Caller | Token | Resource / action | Kỳ vọng |
| --- | --- | --- | --- |
| Alice delegated | `documents.read` | Đọc tài liệu của Alice ở tenant A | ALLOW nếu membership/ACL hợp lệ |
| Alice delegated | `documents.read` | Đọc tài liệu private của Bob ở A | DENY |
| Alice delegated | Không có `documents.edit` | Sửa tài liệu của Alice | DENY |
| Alice delegated | Có `documents.read` | Đọc tài liệu tenant B không có membership | DENY |
| Reporting bot app-only | `reports.generate` | Tạo báo cáo tenant được assign | ALLOW |
| Reporting bot app-only | `documents.read` | Đọc Document không nằm trong app grant | DENY |
| Reporting bot app-only | `documents.read` | `GET /me` của user | DENY |
| Unknown app-only | `documents.read` | Đọc tài liệu bất kỳ | DENY |
| User Alice | `documents.read` | Gọi endpoint internal app-only | DENY |
| User Alice có role admin tenant A | `documents.read` | Admin action tenant B | DENY |
| App-only token có app `roles` | Audience sai | Gọi API nội bộ | Authentication failure |
| Token ID OIDC | `sub=alice`, aud=web-client | Dùng như API access token | DENY |
| Delegated token | Hết hạn | Gọi API | Authentication failure |
| App-only token | Còn hạn, app grant revoked | Truy cập object | DENY theo SLA |
| Delegated token | Còn hạn, membership revoked | Truy cập object | DENY theo SLA |
| App-only token + body userId=alice | Any | "Làm thay Alice" không có delegation proof | DENY |
| Token Exchange hợp lệ | Audience đúng, actor chain đã xác minh | Action trong scope delegation | Theo user + actor + resource policy |
| Remote PDP unavailable | Token hợp lệ | Protected action | Không ALLOW, lỗi an toàn/5xx |

Với app-only/service workflows, test **side effects**, không chỉ HTTP status. Một 403 trả muộn sau khi export hay delete đã chạy vẫn là lỗ hổng.

## 28. Anti-pattern và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Coi mọi `sub` trong JWT là user | Client credentials có thể dùng client ID làm subject | Phân loại actor theo verified token contract |
| App có scope READ nghĩa là user đã cho phép | App-only không có user delegation | App assignment riêng, không có user ngầm |
| Tin `roles` ⇒ app-only | Roles có semantics provider-dependent | Dùng issuer-specific documented claims |
| Tin `scp` ⇒ user trong mọi IdP | Có server phát scopes cho app-only | Verify issuer/token type contract |
| Chỉ kiểm `hasAuthority("SCOPE_documents.read")` | Không biết caller kind hoặc object owner | Domain policy user/app và tenant/ACL |
| Map mọi app role Admin thành ROLE_ADMIN | Service có thể leo thang thành user admin | Namespace/typed principal và limited grants |
| Dùng token của backend đọc dữ liệu theo `userId` body | Confused deputy | Delegated token/OBO hoặc user authorization mạnh |
| Backend copy ID token sang API | Sai audience/semantics | Access token cho resource API |
| Gửi access token audience A sang API B | Token substitution | Validate aud, issue/exchange đúng audience |
| Dùng `client_id` như business user ID | Đồng nhất client và user | Tách client identity và human subject |
| Dùng `Authentication.getName()` để làm owner check cho app | Trùng ID giả/không có user | Resolve verified caller kind trước |
| Tin token còn hạn ⇒ ACL còn active | Revoked grant vẫn có thể stale | Recheck/cache version/introspection policy |
| Dùng consent làm object ACL | Token grant không chứng minh quyền Document42 | Tenant/owner/ACL scoped query |
| Gọi `findAll` bằng app token rồi lọc sau | Data leak, metadata leak, tải lớn | Data-scoped query/DB permissions |
| OAuth app permission = global superuser | Quyền quá rộng và không audit | Least privilege per client, tenant, resource |
| Không log clientId với user token | Khó tìm malicious client | Audit both user subject and client identity |
| App-only audit dùng user giả `system@...` | Mất attribution, nhầm chính sách | Audit APP kind + client ID riêng |
| Dùng user token ở job ban đêm tùy tiện | Token hết hạn/không đúng delegated contract | Service-only flow hoặc approved delegation |
| Token exchange tự ký JWT có `sub=alice` | Không có trusted STS authorization | Dùng flow issuer hỗ trợ và validate chain |
| Cache chung user/app khi cùng scope | ALLOW của bot dùng cho Alice hoặc ngược lại | Cache key caller type, ID, tenant, action, policy |
| Mock JWT test rồi khẳng định chữ ký OK | Mock không kiểm decoder thật | Integration test issuer/signature/audience |
| Đưa client secret trong Git/log/URL | Credential leak | Secret manager, rotation, redaction |
| Không test revoke/tenant changes | Quyền tiếp tục sau offboarding | Freshness SLA và negative tests |
| Tắt toàn bộ authorization khi IdP/PDP lỗi | Fail-open | Không ALLOW; graceful 5xx/deny |

## 29. Checklist thiết kế phân quyền user và application

1. API đang phục vụ **user-delegated**, **app-only** hay cả hai?
2. Có contract chính thức từ IdP để phân biệt hai actor kind không?
3. Resource server xác minh issuer, audience, signature, exp và token type đúng không?
4. Có vô tình chấp nhận OIDC ID token như API access token không?
5. `client_id` và `sub` có được tách đúng khi mapping identity không?
6. Business permission của user có xét tenant membership, owner và ACL không?
7. App-only permission có application assignment theo tenant/resource/action không?
8. Scope có được xem là **điều kiện cần**, không phải quyền truy cập object tự động?
9. Role `ADMIN` có phân biệt user tenant role và app permission không?
10. Endpoint `/me` có từ chối app-only token không?
11. Endpoint background/app-only có từ chối user token không?
12. Backend nhận user request rồi dùng client credentials có nguy cơ confused deputy không?
13. Nếu cần OBO, token exchange có do trusted issuer hỗ trợ và đúng audience không?
14. App có được cấp ít quyền nhất và bị hạn chế tenant/data classification không?
15. Có kiểm tra quyền **trước** export, update, delete, share và enqueue job không?
16. Token/permission caches có caller kind, tenant, action, version và revoke SLA không?
17. Audit có user subject **và** client/service identity khi có delegation không?
18. Service secret được bảo vệ/rotate, không nằm trong logs hay source code không?
19. Tests có tình huống cùng OAuth scope nhưng user/app kết quả khác nhau không?
20. Có integration tests kiểm JWT thực thay vì chỉ mockJwt không?
21. Các route GraphQL, queue, worker, file download, search/export có chung domain policy không?
22. Khi không xác định được actor kind hoặc permission store lỗi, có **deny-by-default** không?

**Kết luận:** Trong OAuth2, **quyền của người dùng** và **quyền của ứng dụng** giải quyết hai bài toán khác nhau. Token delegated mang bối cảnh user đã được ủy quyền; token client credentials xác nhận **chính client** được phép gọi resource server. Scopes/roles trên token cần được xác minh và giải thích theo IdP, nhưng chưa đủ để cấp quyền trên dữ liệu nghiệp vụ. Thiết kế an toàn phải phân loại caller đáng tin, áp policy riêng cho USER và APPLICATION, kiểm tra resource/tenant/action ở server, tránh confused deputy, và kiểm thử cả quyền được cấp lẫn dữ liệu tuyệt đối không được trả về.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): resource owner, client, authorization server, resource server và các grant types.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): PKCE cho authorization code.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `sub`, `client_id`, issuer/audience và khác biệt theo grant có/không có resource owner.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trusted token exchange và actor/delegation.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer access token và xử lý lỗi.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): scope/scp → `SCOPE_*`, JWT validation và `JwtAuthenticationConverter`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): Authorized Client, Authorized Client Manager và các flow client.
- [Spring Security — OAuth2 Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): client credentials cho application/service và authorized client lifecycle (đối chiếu đúng mục theo version).
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và bảo vệ domain service.
- [Microsoft Graph — Permissions Overview](https://learn.microsoft.com/en-us/graph/permissions-overview): delegated permissions so với application permissions theo provider.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, kiểm tra quyền theo action/resource.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): không tin object ID, áp tenant/owner/ACL tại server.
