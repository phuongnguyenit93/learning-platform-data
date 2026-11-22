# Phân biệt nhiều nhà cung cấp với nhiều tổ chức sử dụng ứng dụng (tenant)

> **Chủ đề:** Spring Security – federation. **Nhóm:** Nhiều IdP và tenant. Bài này tách rõ khái niệm **nhiều nhà cung cấp danh tính (multiple Identity Providers – IdP/OP)** với **nhiều tổ chức sử dụng cùng ứng dụng (multi-tenant SaaS)**. Trọng tâm là kiến trúc quan hệ nhiều–nhiều giữa tenant và IdP, quy trình chọn hệ thống đăng nhập, xác minh định danh, ánh xạ người dùng vào tenant và bảo vệ dữ liệu theo tenant trong Java 17+/Spring Security Servlet, OIDC và SAML2.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Định nghĩa chính xác `tenant`, `organization`, `IdP`, `OIDC issuer`, `SAML asserting party`, `client registration`, `Relying Party Registration` và `local account`.
2. Giải thích vì sao **có ba IdP không có nghĩa có ba tenant**, và **có một IdP không có nghĩa ứng dụng chỉ có một tenant**.
3. Thiết kế quan hệ **một–một, một–nhiều, nhiều–một và nhiều–nhiều** giữa tenant và các kết nối IdP.
4. Phân biệt **IdP của khách hàng** với **tenant của chính ứng dụng**; hiểu rằng tenant/realm ở sản phẩm IdP có thể không trùng mô hình tenant của SaaS.
5. Thiết kế bảng registry kết nối, ánh xạ external identity vào local account và membership vào các tenant mà không dựa vào email hay tên miền email làm bằng chứng.
6. Đặt đúng hai lớp kiểm soát: **authentication** (IdP phát chứng cứ hợp lệ cho ứng dụng) và **authorization/tenant isolation** (người này có được xem tài nguyên tổ chức X không?).
7. Cấu hình nhiều `ClientRegistration` OIDC và nhiều `RelyingPartyRegistration` SAML trong Spring Security; phân biệt chúng với mô hình multi-tenant của Resource Server API.
8. Chặn rủi ro **issuer confusion, tenant spoofing, login CSRF, account takeover, cross-tenant data access và BOLA/IDOR**.
9. Kiểm thử đăng nhập qua nhiều IdP, vào nhiều tenant, chuyển tenant, thu hồi membership, session và logout.
10. Chọn được thiết kế onboarding, quản lý cấu hình, certificate/JWKS rotation, audit và hoạt động hàng ngày an toàn.

**Nguyên tắc chính:** **IdP trả lời “ai vừa xác thực người dùng này và chứng minh bằng cách nào?”**; **tenant trả lời “tổ chức nào sở hữu dữ liệu và ngữ cảnh nghiệp vụ mà người dùng định truy cập?”**. Hai câu hỏi có thể liên quan nhưng **không được gộp thành một**.

## 2. Các thuật ngữ: cùng một chữ “tenant”, nhiều nghĩa

| Thuật ngữ | Nghĩa trong hệ thống | Ví dụ | Có đồng nghĩa với IdP/tenant khác? |
| --- | --- | --- | --- |
| **Application tenant** | Tổ chức/khách hàng sở hữu không gian dữ liệu, cấu hình và quyền trong SaaS | `org-red`, `org-blue` | Không nhất thiết tương ứng 1:1 IdP |
| **Tenant của nhà cung cấp danh tính** | Miền quản trị/đối tượng định danh ở sản phẩm IdP; có thể là directory, realm, domain hoặc tenant identifier | `realm=staff`, directory khách hàng | Có thể phục vụ nhiều application tenants, hoặc một app tenant có nhiều IdP directories |
| **Identity Provider (IdP)** | Hệ thống xác thực danh tính và phát SAML Assertion | Công cụ SAML tập trung, IdP đối tác | Không tự là application tenant |
| **OpenID Provider (OP)** | Issuer phát OIDC ID Token cho Relying Party | `https://login.example.net/realms/staff` | Một issuer có thể quản lý nhiều nhóm/tổ chức |
| **OIDC `issuer`** | Định danh nguồn phát ID Token, thường là HTTPS URI phải khớp chính xác | `iss=https://login.example.net/realms/staff` | Không phải `tenantId` của dữ liệu SaaS |
| **SAML `entityID` IdP** | Định danh logic Asserting Party trong metadata/assertion | `https://sso.partner.example/idp` | Không phải tên tenant SaaS |
| **OIDC `ClientRegistration`** | Cấu hình client ID, secret/PKCE, issuer, callback, scopes; được chọn bằng `registrationId` | `staff-oidc` | Một IdP có thể có nhiều client registrations |
| **SAML `RelyingPartyRegistration`** | Liên kết cụ thể giữa SP và IdP: `registrationId`, entityID, ACS, certificates | `partner-saml` | Một IdP có thể có nhiều RP registrations; mỗi registration không đương nhiên một application tenant |
| **External identity** | Người dùng theo issuer và subject đã được xác minh | `(iss,sub)` hoặc SAML stable NameID | Không tự quyết định membership trong tenant |
| **Local account** | ID tài khoản do ứng dụng quản lý | `accountId=8a...` | Có thể liên kết nhiều external identities |
| **Tenant membership** | Quan hệ `(localAccountId, tenantId, role/status)` của ứng dụng | User có `REPORT_VIEW` ở `org-red` | Cấp quyền nghiệp vụ; khác việc xác thực thành công |
| **Authorization context** | Tenant đang được chọn, actor và phạm vi dữ liệu/hành động | `activeTenant=org-red` | Phải được kiểm tra với membership ở mỗi quyết định cần thiết |

**Ví dụ tên dễ gây nhầm:** Microsoft Entra “tenant”, Keycloak “realm” và “tenant” trong một phần mềm CRM đều có thể trông như một tổ chức. Tuy nhiên, chúng nằm ở các **lớp quản trị khác nhau**. Có thể ánh xạ chúng 1:1 theo một hợp đồng triển khai, nhưng đó là **quy tắc cấu hình riêng**, không phải định luật của giao thức.

### 2.1. Nhiều IdP (multiple identity providers) là gì?

Một ứng dụng chấp nhận đăng nhập qua nhiều hệ thống danh tính, ví dụ:

- Nhân viên sử dụng OP OIDC của công ty.
- Nhà thầu sử dụng SAML IdP của đối tác.
- Khách hàng sử dụng OP OIDC khác.
- Người dùng được broker xác thực từ IdP upstream và nhận assertion/token qua một issuer tập trung.

Bài toán kỹ thuật chủ yếu là **chọn đúng registration**, kiểm tra issuer/khóa/chữ ký/token/response, ánh xạ external subject đã xác minh vào local user. Ứng dụng có thể **chỉ chứa một tổ chức** nhưng chấp nhận cả ba IdP.

### 2.2. Nhiều tenant là gì?

Một ứng dụng SaaS phục vụ nhiều tổ chức cùng product/backend (có thể cùng database hoặc tách cơ sở dữ liệu). Mỗi tenant có dữ liệu riêng, người dùng, quyền, giới hạn, cấu hình và vòng đời tổ chức riêng.

Bài toán chính là **cô lập dữ liệu và quyền**, không chỉ chọn nơi đăng nhập. Một OP có thể xác thực người dùng của **mọi tenant** trong SaaS, nhưng ứng dụng vẫn phải xác minh membership, resource ownership và authorization của từng request.

### 2.3. Không nên coi hai khái niệm là biến thể của nhau

```text
                IDENTITY PLANE
        +-------------------------------+
        | OP A (OIDC) | IdP B (SAML)    |
        | OP C (OIDC) | Broker D        |
        +----------+--------------------+
                   |
                   | ID Token / Assertion / Ticket
                   | đã xác minh cho RP/SP
                   v
        +-------------------------------+
        | Application Authentication     |
        | External identity -> accountId |
        +-------------------------------+
                   |
                   | Policy / membership
                   v
                TENANCY PLANE
        +-------------------------------+
        | Tenant RED  | Tenant BLUE      |
        | Tenant GOLD | Tenant GREEN     |
        +-------------------------------+
                   |
                   | tenant + object authorization
                   v
        +-------------------------------+
        | Data / Reports / Orders / APIs |
        +-------------------------------+
```

**Identity plane** nói về độ tin cậy của danh tính. **Tenancy plane** nói về quyền sở hữu dữ liệu và chính sách kinh doanh. Có giao điểm giữa hai miền: một tenant **có thể** giới hạn những IdP mà thành viên của họ được dùng, nhưng giới hạn đó vẫn không thay thế kiểm tra membership.

## 3. Bốn kiểu ánh xạ và ví dụ dễ hình dung

| Mô hình | Các quan hệ | Tình huống hợp lệ | Điều không được suy ra |
| --- | --- | --- | --- |
| **1 tenant – 1 IdP** | `org-red ↔ IdP Red` | Khách hàng dùng IdP doanh nghiệp riêng | IdP Red không thể có user ở tenant khác |
| **1 tenant – nhiều IdP** | `org-red ↔ Staff OIDC` và `Partner SAML` | Nhân viên và nhà cung cấp cùng vào một không gian làm việc | Hai người từ hai IdP có cùng email là cùng một người |
| **Nhiều tenant – 1 IdP** | `org-red`, `org-blue` đều dùng `Corporate OIDC` | Một tập đoàn điều hành nhiều công ty con/nhóm dự án | Một user Corporate OIDC có quyền đọc mọi tenant |
| **Nhiều tenant – nhiều IdP** | `org-red ↔ Corporate OIDC + Partner SAML`; `org-blue ↔ Corporate OIDC + External OIDC` | SaaS B2B đa tổ chức, đa mạng lưới đối tác | Có thể coi issuer là tenantId hoặc một role áp toàn hệ thống |

**Mô hình 1 tenant – nhiều IdP:** User Red A đến từ Corporate OIDC, User Red B đến từ SAML Partner. Cả hai có thể được cấp quyền báo cáo Red nếu membership hợp lệ. Đừng biến IdP Partner thành một tenant mới chỉ vì đây là nhà cung cấp thứ hai.

**Mô hình nhiều tenant – 1 IdP:** Người dùng có một tài khoản OIDC từ Corporate OP, được phân quyền truy cập Red và Blue. Mỗi lần chọn Red hay Blue, session có thể giữ cùng một principal, nhưng query và thao tác phải lọc `tenantId` tương ứng. Không tạo thêm OIDC issuer nhân tạo chỉ để mô tả Blue.

**Mô hình nhiều–nhiều:** Một người từ Corporate OP có thể ở Red và Blue, trong khi đối tác từ Partner SAML chỉ ở Red. Tenant Gold sử dụng riêng OP Gold. Thay đổi membership Red không được vô tình thay đổi xác thực hoặc quyền ở Blue/Gold.

### 3.1. Ma trận kết nối minh họa

| Application tenant | Corporate OIDC (`corp-oidc`) | Partner SAML (`partner-saml`) | Gold OIDC (`gold-oidc`) |
| --- | --- | --- | --- |
| `org-red` | Cho phép làm nguồn đăng nhập | Cho phép làm nguồn đăng nhập | Không cho |
| `org-blue` | Cho phép làm nguồn đăng nhập | Không cho | Không cho |
| `org-gold` | Không cho | Không cho | Cho phép làm nguồn đăng nhập |

Bảng này chỉ là **policy tenant → authentication connection**. Nó **không phải** bảng quyền của từng user. Để đọc báo cáo Red, ứng dụng còn cần bản ghi membership:

```text
localAccountId=acct-100
externalIdentity=(corp-oidc, issuer=https://login.corp.example/realms/staff, sub=em-77)
memberships:
  (acct-100, org-red, REPORT_READ, ACTIVE)
  (acct-100, org-blue, REPORT_VIEW, ACTIVE)

localAccountId=acct-200
externalIdentity=(partner-saml, issuer=https://sso.partner.example/entity, stableNameID=p-42)
memberships:
  (acct-200, org-red, REPORT_READ, ACTIVE)
```

Khi `acct-100` truy cập `org-gold`, **phải từ chối** dù người dùng đã đăng nhập thành công tại Corporate OIDC. Không tồn tại quan hệ nối `Corporate → Gold` hoặc membership cụ thể của người ấy.

## 4. Những identifier thường phải quản lý tách biệt

Hãy đặt tên rõ trong schema, code và log:

```text
tenantId                     = "org-red"
connectionId                 = "corp-oidc-for-red"
protocol                     = "OIDC"
clientRegistrationId         = "corp-oidc"
providerId                   = "corporate-op"
issuer                       = "https://login.corp.example/realms/staff"
externalSubject              = "em-77"
localAccountId               = "acct-100"
membershipRole               = "REPORT_READ"
currentTenant                = "org-red"
```

Trong SAML:

```text
tenantId                     = "org-red"
connectionId                 = "partner-saml-for-red"
protocol                     = "SAML2"
relyingPartyRegistrationId   = "partner-saml"
idpEntityId                  = "https://sso.partner.example/entity"
spEntityId                   = "https://app.example.org/saml2/service-provider-metadata/partner-saml"
assertionConsumerService     = "https://app.example.org/login/saml2/sso/partner-saml"
externalSubject              = stable NameID + qualifier theo hợp đồng
localAccountId               = "acct-200"
```

- `tenantId` là **namespace nghiệp vụ**. Dù user đổi IdP, tenant và dữ liệu tổ chức vẫn có thể giữ nguyên.
- `clientRegistrationId`/`relyingPartyRegistrationId` là **khóa tra cấu hình của framework**; tùy thiết kế có thể dùng chung cho nhiều tenant hoặc tạo một registration per-tenant.
- `issuer`/IdP `entityID` là **định danh nguồn phát bằng chứng**; nó được xác minh bằng cấu hình IdP tin cậy và không phải là `tenantId`.
- `sub` trong OIDC ổn định **trong phạm vi issuer**; với pairwise subject identifier, cùng người có thể có `sub` khác nhau giữa clients/sector identifiers. Không tự gộp.
- SAML `NameID` có nhiều format; `transient` không phù hợp làm khóa nội bộ lâu dài, `persistent`/attribute immutable phải được đánh giá đúng contract; NameID không tự bằng email.
- `localAccountId` nên là ID do application cấp, không dùng địa chỉ email, displayName, user-supplied tenant slug hay raw `sub` làm primary key toàn hệ thống.
- `membershipRole` là quyền ở **một tenant cụ thể**, không tự động là quyền global admin.

### 4.1. Đừng đồng nhất OIDC token audience và application tenant

Trong OIDC login, ID Token `aud` phải chứa **OAuth client_id của RP**; đó không phải `tenantId` SaaS. Một token hợp lệ cho client `web-portal` có thể được dùng để **xác thực người dùng** trước khi ứng dụng quyết định user thuộc Red hay Blue. Không thay `aud` thành `org-red` chỉ vì người dùng chọn tenant Red.

Trong SAML, `AudienceRestriction` phải phù hợp **SP entityID** được đăng ký. Nếu cùng một SP phục vụ nhiều tenant, có thể có chiến lược một SP entityID chung hoặc nhiều SP registrations với entityID riêng theo tenant. Dù lựa chọn nào, audience chỉ chứng minh assertion dành cho RP/SP nào, **không tự chứng minh permission đọc tài nguyên của một organization**.

### 4.2. Vì sao email domain không xác định tenant an toàn?

Một người có `user@red.example` có thể là nhân viên, nhà thầu, khách dùng alias hoặc mailbox bị tái cấp phát; email có thể đổi, chưa verified hoặc do IdP khác phát. Một tổ chức có thể sử dụng nhiều email domains và một domain có thể phục vụ nhiều đơn vị. **Không lấy `email.endsWith("@red.example")` làm bằng chứng membership**, không tự link tài khoản của hai IdP có email trùng, và không dùng `preferred_username` làm khóa định danh.

Email domain có thể giúp **home realm discovery** như một gợi ý UX: “Có thể bạn muốn đăng nhập qua Corporate”. Sau login vẫn phải xác minh issuer+subject và truy vấn membership ở server.

## 5. Quy trình người dùng đăng nhập từ một tenant cụ thể

Một phương án SaaS hỗ trợ đường dẫn:

```text
https://app.example.org/t/org-red/login
https://app.example.org/t/org-blue/login
```

Trình tự:

```text
[Browser GET /t/org-red/login]
          |
          v
[Server resolve org-red từ registry của app]
          |
          v
[Đọc các authentication connections đang ACTIVE cho Red]
          |
          v
[Hiển thị "Corporate OIDC" / "Partner SAML" theo policy]
          |
          v
[User chọn 1 connection đã được duyệt]
          |
          v
[Spring khởi tạo OIDC / SAML theo registrationId]
          |    state/nonce/PKCE hoặc SAML Request ID/RelayState
          |    ràng buộc tenant-intent và anti-CSRF với phiên
          v
[Browser được chuyển tới IdP đã phê duyệt]
          |
          v
[IdP xác thực và gửi chứng cứ về callback của RP/SP]
          |
          v
[Spring kiểm tra issuer/chữ ký/audience/time/correlation]
          |
          v
[Server resolve external identity -> localAccountId]
          |
          v
[Server kiểm tra connection cho Red + ACTIVE membership Red]
          |
       ALLOWED?
       /      \
      NO       YES
      |         |
      v         v
 [403/deny] [Thiết lập activeTenant=Red trong session server]
                |
                v
        [Authorize từng object theo Red]
```

**Trường `tenantId` trên URL ban đầu chỉ là ngữ cảnh yêu cầu, chưa phải kết quả được cấp quyền.** Không tin `tenantId` chỉ vì nó xuất hiện trong URL đã được client gọi. Sau callback, server phải đối chiếu tenant-intent đã được bảo vệ bởi login state/request repository và quyền thành viên hiện tại. Nếu thiếu/không còn quyền, không tạo tenant-scoped session hoặc không cấp quyền truy cập Red.

### 5.1. Home realm discovery khác authorization

Ứng dụng có thể tìm IdP dựa trên:

- Tenant slug đã nhập trên trang đăng nhập.
- Organization code do khách hàng cung cấp.
- Email domain do người dùng gõ.
- Nút đăng nhập hiển thị sẵn.
- Hostname/subdomain như `red.app.example.org`.

Những dữ liệu này **chỉ giúp chọn IdP** trước khi có danh tính đã xác minh. Chúng có thể bị giả mạo hoặc sai. Không cho việc nhập `red` trong URL tự tạo membership Red. Nếu nguồn IdP được chọn không nằm trong danh sách được phép cho Red, từ chối trước khi redirect.

**Subdomain/Host phải đáng tin:** Reverse proxy cần chặn Host lạ, xóa `X-Forwarded-Host` từ client và chỉ truyền giá trị đã được kiểm soát. Không dùng raw HTTP header do client tự chọn để tạo một issuer/JWKS URL, ACS URL hoặc database tenant. Nếu có vanity domains, map theo bảng đã xác minh quyền sở hữu domain.

### 5.2. Không lấy tenant từ một `state`/`RelayState` chưa kiểm tra

OIDC dùng `state` để chống login CSRF và ràng buộc response với request; `nonce` ràng buộc ID Token với authorization request khi áp dụng. SAML dùng `AuthnRequest ID`, `InResponseTo`, `RelayState` và session/request repository theo profile. Nếu ứng dụng cần nhớ tenant-intent qua redirect, hãy lưu ở **server-side session hoặc kho correlation đã ký/được bảo vệ** và ràng buộc với request. Đừng dùng `?tenant=org-red` trong callback hoặc raw `RelayState` làm câu trả lời cuối cùng về tenant mà user đã được cấp quyền.

Nếu user mở song song hai tab login cho Red/Blue, cần đảm bảo correlation phân biệt từng flow. Không lưu một biến global `currentTenantPending` rồi để callback muộn của tab B ghi đè tab A.

### 5.3. IdP-initiated SAML và “không biết người dùng bắt đầu từ tenant nào”

Trong **SP-initiated SAML SSO**, Spring có thông tin request registration và correlation; tenant-intent có thể được bảo vệ trong flow. Với **IdP-initiated (unsolicited) SAML SSO**, không có `AuthnRequest` ban đầu, nên SP cần chính sách rõ: có chấp nhận unsolicited SSO không, làm sao resolve RP registration, nguồn issuer, tenant, account và membership?

**Không suy ra tenant từ issuer một cách vô điều kiện** nếu IdP dùng chung cho nhiều tổ chức. Có thể yêu cầu user chọn tenant **sau khi** xác thực, hoặc buộc SP-initiated flow cho các vùng tenant nhạy cảm. Không tự map vào tenant đầu tiên được tìm thấy hay tenant admin chỉ vì SAML response đến từ IdP tin cậy.

## 6. Một IdP phục vụ nhiều tenant: vấn đề chính là quyền sau login

Ví dụ Corporate OIDC có issuer `https://login.corp.example/realms/staff`. Hàng nghìn nhân viên từ đó có thể vào Red, Blue hoặc cả hai. Spring xác minh ID Token từ một issuer đã tin. Sau đó ứng dụng phải kiểm tra:

1. User external key là `(issuer,sub)`; đã liên kết với `localAccountId` nào?
2. Account có `ACTIVE` hay đã bị khóa?
3. Tenant Red tồn tại và `ACTIVE`?
4. User có `membership(accountId,Red)` ACTIVE không?
5. Người này có role/permission cần thiết trong Red không?
6. Tài nguyên `report-123` thực sự thuộc Red không?
7. Chính sách bổ sung, như owner, phòng ban, approval, MFA, thời gian, có được đáp ứng không?

Nếu user được thêm vào Blue sau đó, **không cần sinh issuer OIDC thứ hai** chỉ để diễn đạt membership mới. Cập nhật bản ghi membership. Nếu user bị xóa khỏi Red, việc xác thực bằng issuer Corporate vẫn hợp lệ cho Blue, nhưng quyền Red phải bị thu hồi. Không hủy mọi quyền ở các tenant còn lại nếu không có yêu cầu.

### 6.1. Claim `groups` từ IdP không tự là membership SaaS

IdP có thể phát nhóm `staff`, `finance`, `partner-admin`. Những tên này chỉ có ý nghĩa theo issuer/tenant/directory nguồn. Nếu chính sách muốn map group vào membership hoặc role tenant, cần bảng explicit:

```text
(provider/issuer, externalGroupId, tenantId) -> permissionSet

(corp-oidc, "grp-red-reader", org-red)  -> REPORT_READ
(corp-oidc, "grp-blue-reader", org-blue)-> REPORT_READ
(partner-saml, "grp-red-ext", org-red)   -> REPORT_READ_LIMITED
(other-idp, "Admin", any)               -> DENY unless approved
```

Nếu một nhóm IdP bị đổi tên, đừng tự cấp quyền cho mọi nhóm chứa chuỗi `admin` hoặc dùng `endsWith("read")`. Trường hợp quyền nhạy cảm, có thể cần nguồn quyền **do ứng dụng/quản trị tổ chức** kiểm soát ngoài membership của IdP.

## 7. Một tenant dùng nhiều IdP: vấn đề chính là nguồn danh tính

Tenant Red cho đăng nhập qua Corporate OIDC và Partner SAML. Cả hai có thể chứa người trùng email hoặc display name; vẫn là **external identities khác nhau**. Một người có thể chủ động liên kết chúng vào một local account nếu qua quy trình bảo mật phù hợp. Không tự ghép.

Với OIDC, ID Token cần xác minh `iss`, `aud`, chữ ký, `exp`, `nonce`/state của authorization flow; định danh ổn định trong phạm vi issuer là `iss + sub`. Với SAML, cần IdP issuer, signing certificate, `AudienceRestriction` cho SP entityID, `Recipient`/`Destination` cho ACS, `InResponseTo`, clock skew và replay.

**Tình huống trùng email:**

```text
OIDC Corporate:
  iss = https://login.corp.example/realms/staff
  sub = emp-77
  email = lan@example.org

SAML Partner:
  IdP entityID = https://sso.partner.example/entity
  persistent NameID = partner-1007
  mail = lan@example.org

Application:
  ExternalKey A != ExternalKey B
  => KHÔNG tự link cùng local account.
```

Nếu account linking được phép, người dùng phải chứng minh quyền kiểm soát account hiện tại và external identity mới, có step-up/approval khi rủi ro cao, audit và unique constraints. Email (kể cả `email_verified=true` của OP) là một claim liên hệ, **không phải mật khẩu chứng minh sở hữu local account**.

### 7.1. Có nên tạo một client registration cho mỗi tenant?

**Không có đáp án duy nhất; quyết định dựa trên ranh giới trust và vận hành.**

- **Một registration chung cho nhiều tenants:** Hợp lý khi cùng issuer, cùng client_id/SP entityID, cùng chính sách SSO, cùng callback và cùng bộ khóa; dữ liệu tenant được tách **sau login**. Ít cấu hình, nhưng yêu cầu membership/tenant isolation nghiêm ngặt.
- **Một registration cho mỗi tenant:** Hợp lý khi mỗi khách hàng cần client ID riêng, redirect URI/ACS riêng, metadata SP riêng, chứng thư SP ký riêng, logout khác nhau, IdP policies tách biệt hoặc tenant tự quản trị federation. Tăng số lượng registrations và overhead vòng đời.
- **Một issuer có nhiều client IDs:** Nhiều OIDC `ClientRegistration` có thể trỏ về cùng `issuer-uri` nhưng khác client_id/secret/redirect_uri. Đừng đếm registrations rồi coi chúng là số IdP hoặc số tenant.
- **Một SAML IdP có nhiều SP registrations:** Có thể cùng `asserting party entityID` nhưng SP `entityID`/ACS khác nhau theo tenant, nhất là yêu cầu ký hay audience khác nhau.

**Một–một là lựa chọn triển khai**, không phải ràng buộc của OIDC hay SAML. Ghi rõ ánh xạ `tenantId → allowedConnectionIds → registrationId/issuer`, thay vì nhồi tất cả khái niệm vào một cột `provider`.

## 8. Thiết kế database/registry tách bốn lớp

Một schema quan hệ điển hình:

```text
APPLICATION_TENANT
  tenant_id PK
  slug UNIQUE
  status
  plan
  isolation_mode

IDENTITY_PROVIDER
  provider_id PK
  protocol
  issuer_or_idp_entity_id
  metadata_source_or_discovery
  trust_config_version
  status

AUTHENTICATION_CONNECTION
  connection_id PK
  provider_id FK
  spring_registration_id
  client_id_or_sp_entity_id
  callback_or_acs
  lifecycle_status
  owner

TENANT_AUTH_CONNECTION
  tenant_id FK
  connection_id FK
  enabled
  home_realm_priority
  PRIMARY KEY (tenant_id, connection_id)

EXTERNAL_IDENTITY
  external_identity_id PK
  verified_issuer
  stable_subject
  source_qualifiers
  local_account_id FK
  UNIQUE (verified_issuer, stable_subject, relevant_qualifiers)

LOCAL_ACCOUNT
  local_account_id PK
  lifecycle_status
  display_profile

TENANT_MEMBERSHIP
  tenant_id FK
  local_account_id FK
  membership_status
  membership_role_version
  PRIMARY KEY (tenant_id, local_account_id)

TENANT_ROLE_ASSIGNMENT
  tenant_id FK
  local_account_id FK
  permission_code
  scope
  PRIMARY KEY (...)
```

**Giải thích:**

- `IDENTITY_PROVIDER` mô tả **nguồn**. Một nhà cung cấp về mặt thương hiệu có thể có nhiều issuers/realms; khóa tin cậy nên theo **issuer/IdP entityID thực sự**, không chỉ tên hãng.
- `AUTHENTICATION_CONNECTION` mô tả **một cách ứng dụng kết nối** vào nguồn. Một provider có thể có nhiều connections/registrations.
- `TENANT_AUTH_CONNECTION` là bảng many-to-many xác định tenant được dùng connection nào. Không suy ra membership từ bảng này.
- `EXTERNAL_IDENTITY` phải chứa định danh ổn định đã được verify; đối với SAML, thêm NameIDFormat/NameQualifier/SPNameQualifier hoặc immutable attribute nếu contract yêu cầu để tránh trùng khóa; đối với OIDC, cặp `iss+sub` là gốc.
- `TENANT_MEMBERSHIP` là **quyết định người–tổ chức**. Cùng account có thể là thành viên nhiều tenant với roles khác nhau.
- `TENANT_ROLE_ASSIGNMENT` nên chứa permission/role được quản trị có audit. Authority `ROLE_ADMIN` “global” có thể không phù hợp khi quyền quản trị chỉ được áp dụng ở Red.
- `lifecycle_status` cho phép khóa một IdP connection nhưng giữ nguyên dữ liệu tenant; khóa tenant nhưng không tự xóa external identity thuộc nhiều tenant khác.

### 8.1. Quy tắc unique và invariant có giá trị bảo mật

1. `tenantId`/`accountId` do ứng dụng cấp, không lấy trực tiếp từ email.
2. OIDC external identity theo `issuer + sub`, kiểm tra đúng issuer đã đăng ký; với pairwise subject, không ép identity xuyên client.
3. Một external identity chỉ được link sang **một local account** ở một thời điểm, trừ khi mô hình đã thiết kế rõ multi-account và có quy tắc riêng.
4. Mỗi active connection chỉ được phép trỏ tới provider/issuer đã phê duyệt; đổi issuer/cert/client_id yêu cầu change approval.
5. Một user có role khác nhau theo tenant; không lưu global role dưới dạng string đơn giản rồi áp cho tất cả tenants.
6. Tenant status và membership status kiểm tra ở các điểm truy cập thích hợp; không giữ quyền cũ vô thời hạn trong session.
7. Tài nguyên phải có `tenant_id` hoặc ranh giới lưu trữ tương đương; không dựa duy nhất vào bộ lọc UI.
8. Bản ghi audit chứa cả `actor account`, `active tenant` và `connection/issuer` đã xác minh.

## 9. Java 17 chạy độc lập: chứng minh provider ≠ tenant

Ví dụ dưới đây là **mô hình quyền đã có danh tính được xác minh**, không thực hiện OIDC/SAML, không đọc JWT, không ký XML. Nó kiểm tra ba điều kiện riêng: connection thuộc issuer được cấu hình, tenant chấp nhận connection, và external identity có membership ở tenant đó.

File `ProviderVsTenantDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class ProviderVsTenantDemo {

    record Provider(String id, String issuer) { }

    record Tenant(String id, Set<String> allowedProviders) { }

    record ExternalIdentity(String issuer, String subject) { }

    static final String STAFF_ISSUER =
        "https://login.corp.example/realms/staff";
    static final String PARTNER_ISSUER =
        "https://login.partner.example/issuer";

    static final Map<String, Provider> PROVIDERS = Map.of(
        "staff", new Provider("staff", STAFF_ISSUER),
        "partner", new Provider("partner", PARTNER_ISSUER)
    );

    static final Map<String, Tenant> TENANTS = Map.of(
        "red", new Tenant("red", Set.of("staff", "partner")),
        "blue", new Tenant("blue", Set.of("staff")),
        "gold", new Tenant("gold", Set.of("partner"))
    );

    // Trong thực tế, đây là dữ liệu membership có thẩm quyền ở server,
    // không được tạo từ claim tenant tự khai của browser.
    static final Map<ExternalIdentity, Set<String>> MEMBERSHIPS =
        Map.of(
            new ExternalIdentity(STAFF_ISSUER, "u-42"),
            Set.of("red", "blue"),
            new ExternalIdentity(PARTNER_ISSUER, "u-42"),
            Set.of("gold")
        );

    static boolean mayEnter(
            String tenantId,
            String providerId,
            ExternalIdentity identity) {

        Tenant tenant = TENANTS.get(tenantId);
        Provider provider = PROVIDERS.get(providerId);
        if (tenant == null || provider == null || identity == null) {
            return false;
        }

        boolean issuerMatches =
            provider.issuer().equals(identity.issuer());
        boolean tenantAllowsProvider =
            tenant.allowedProviders().contains(providerId);
        boolean userIsMember =
            MEMBERSHIPS.getOrDefault(identity, Set.of())
                .contains(tenantId);

        return issuerMatches && tenantAllowsProvider && userIsMember;
    }

    public static void main(String[] args) {
        ExternalIdentity staff =
            new ExternalIdentity(STAFF_ISSUER, "u-42");
        ExternalIdentity partner =
            new ExternalIdentity(PARTNER_ISSUER, "u-42");

        System.out.println("providers=" + PROVIDERS.size());
        System.out.println("tenants=" + TENANTS.size());
        System.out.println("staffRed=" +
            mayEnter("red", "staff", staff));
        System.out.println("staffBlue=" +
            mayEnter("blue", "staff", staff));
        System.out.println("staffGold=" +
            mayEnter("gold", "staff", staff));
        System.out.println("partnerGold=" +
            mayEnter("gold", "partner", partner));
        System.out.println("partnerRed=" +
            mayEnter("red", "partner", partner));
        System.out.println("sameExternalIdentity=" +
            staff.equals(partner));
        System.out.println("unknownTenant=" +
            mayEnter("unknown", "staff", staff));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 ProviderVsTenantDemo.java
java ProviderVsTenantDemo
```

Stdout xác định:

```text
providers=2
tenants=3
staffRed=true
staffBlue=true
staffGold=false
partnerGold=true
partnerRed=false
sameExternalIdentity=false
unknownTenant=false
```

**Điểm cần đọc từ kết quả:**

- Có **2 providers** nhưng **3 tenants**: hai con số độc lập.
- Staff identity có quyền vào Red và Blue, mặc dù cả hai chỉ dùng một issuer Staff.
- Partner và Staff đều có `subject="u-42"`, nhưng issuer khác nên `ExternalIdentity` khác.
- Tenant Red chấp nhận provider Partner về cấu hình, nhưng specific partner identity **không có membership Red**, nên `partnerRed=false`.
- Tenant Gold không cho Staff provider, nên `staffGold=false`; kể cả nếu user gửi query `?tenant=gold` thì không được bypass.

**Giới hạn quan trọng:** Demo giả định các `ExternalIdentity` đã qua xác minh giao thức ở một tầng khác. Production cần tra local account, membership, role-permission và object ownership; không nhận record `ExternalIdentity` do client dựng rồi gọi `mayEnter` để thay thế authentication. Mã trên cố tình dùng cùng một giá trị `sub` cho hai issuer để chứng minh **không được chỉ so subject string**.

## 10. Spring Security OIDC: nhiều registration không nhất thiết nhiều tenant

### 10.1. Spring Boot YAML cho nhiều OpenID Providers

Dự án Spring Boot servlet với `spring-boot-starter-security` và `spring-boot-starter-oauth2-client` có thể cấu hình hai client registrations:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff-oidc:
            provider: corp
            client-id: portal-staff
            client-secret: ${STAFF_OIDC_CLIENT_SECRET}
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          partner-oidc:
            provider: partner
            client-id: portal-partner
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: https://login.corp.example/realms/staff
          partner:
            issuer-uri: https://login.partner.example/issuer
```

**Các domain/client IDs ở đây chỉ là cấu hình minh họa.** Muốn chạy phải thay bằng OP thật được phê duyệt, giữ secrets trong secret manager/environment, đăng ký exact redirect URI HTTPS tại từng OP và kiểm tra issuer discovery/tokens. Không hard-code client secrets vào source.

Khi bật `http.oauth2Login(...)`, các đường mặc định thường là:

- `GET /oauth2/authorization/staff-oidc`: bắt đầu login qua client registration `staff-oidc`.
- `GET /oauth2/authorization/partner-oidc`: bắt đầu login qua `partner-oidc`.
- `GET /login/oauth2/code/staff-oidc` hoặc `.../partner-oidc`: callback xử lý authorization code tương ứng.

**Điều này chỉ chứng minh ứng dụng có hai lựa chọn đăng nhập, không tạo tenant tự động.** Nếu cả Red và Blue muốn sử dụng `staff-oidc`, server có thể hiển thị cùng link khi user bắt đầu từ Red/Blue; ngữ cảnh tenant cần được lưu/ràng buộc an toàn rồi kiểm tra membership sau khi callback.

### 10.2. `provider` trong Spring Boot là tên cấu hình, không phải `tenantId`

Trong YAML, `registration.staff-oidc.provider: corp` tham chiếu mục `provider.corp`. Cùng `provider.corp` có thể được nhiều client registrations dùng (ví dụ client ID cho ứng dụng mobile và web hoặc tenant có yêu cầu riêng). **Tên `corp` là khóa cấu hình**, còn OIDC `issuer-uri` là danh tính của OP, `client-id` là audience của ID Token và `tenantId` là dữ liệu ứng dụng.

Không lấy chuỗi `registrationId` để suy ra:
- Token chắc chắn đến từ issuer nào mà không kiểm chứng;
- User thuộc tenant nào;
- User có quyền vào `/t/org-red/**`;
- Những dữ liệu đã được user đồng ý truy cập.

Khi một callback được xử lý, Spring Security cần đối chiếu `state`, client registration và ID Token (chữ ký/issuer/audience/nonce), rồi mới cho ứng dụng xây tenant context dựa trên membership.

### 10.3. Một issuer, nhiều client registrations

Ví dụ hai registrations `red-oidc` và `blue-oidc` cùng trỏ `provider: corp` nhưng có client IDs khác nhau theo hợp đồng của khách. Đây là **2 client registrations**, **1 OP issuer**, có thể là **2 app tenants** nếu kiến trúc đã định rõ, nhưng không tự luôn 2 tenants.

Với OIDC `pairwise sub`, cùng một con người có thể nhận `sub` khác nhau giữa clients/sector IDs. Khi cần account linking, dùng phương thức có bằng chứng của user; không suy từ email hoặc “cùng OP thì cùng subject”. Tài liệu OIDC Core bảo đảm cặp `iss+sub` là định danh trong phạm vi issuer và trường hợp pairwise có tính phụ thuộc client/sector.

### 10.4. Khi IdP của một nhà cung cấp có nhiều issuers

Một nhà cung cấp thương hiệu có thể phát ID Tokens từ các realms/directories/tenants khác nhau. Ví dụ `https://login.example/realms/a` và `https://login.example/realms/b` là hai issuers khác nhau theo OIDC, dù cùng hostname. **Issuer là giá trị case-sensitive và path có ý nghĩa**; Spring phải kiểm tra chính xác expected `iss`, không chấp nhận một namespace rộng chỉ vì token được ký bằng khóa nằm trên cùng domain.

Do đó “nhiều IdP” đôi khi là nhiều endpoint issuer của cùng sản phẩm, và “nhiều tenant IdP” không luôn tương đương “nhiều tổ chức SaaS”.

## 11. Spring Security SAML2: nhiều relying-party registrations

Với `spring-security-saml2-service-provider`, có thể cấu hình nhiều SAML connections trong `spring.security.saml2.relyingparty.registration`. Ví dụ:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          red-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/red-saml"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/red-saml"
            assertingparty:
              entity-id: "https://idp.red.example/entity"
              verification:
                credentials:
                  - certificate-location: classpath:saml/red-idp.crt
              singlesignon:
                url: "https://idp.red.example/sso"
                binding: REDIRECT
          blue-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/blue-saml"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/blue-saml"
            assertingparty:
              entity-id: "https://idp.blue.example/entity"
              verification:
                credentials:
                  - certificate-location: classpath:saml/blue-idp.crt
              singlesignon:
                url: "https://idp.blue.example/sso"
                binding: REDIRECT
```

File certificates phải là **IdP signing certificates thật** đã xác minh; các `example` domains là ví dụ. Nếu IdP yêu cầu signed AuthnRequest, bổ sung **SP signing credentials** và chính sách ký tương ứng; không bỏ yêu cầu chỉ để login được.

Khi bật `saml2Login`, các endpoint điển hình:

- `GET /saml2/authenticate/red-saml`: tạo `AuthnRequest` theo `RelyingPartyRegistration` red.
- `GET /saml2/authenticate/blue-saml`: tạo request theo blue.
- `POST /login/saml2/sso/red-saml` hoặc `.../blue-saml`: SP xử lý `SAMLResponse` tại ACS, dùng đúng registration.
- `GET /saml2/metadata/red-saml` và `.../blue-saml` khi `saml2Metadata` được bật: công bố SP metadata riêng cho kết nối.

Mặc dù ví dụ dùng tên `red-saml` và `blue-saml`, **registrationId không nhất thiết phải trùng tenantId**. Nếu một IdP doanh nghiệp phục vụ Red và Blue qua một SP registration chung, user vẫn cần được kiểm tra quyền tenant sau SAML login. Ngược lại, nếu Red dùng hai IdP SAML, hai registrations có thể cùng liên kết với application tenant Red qua bảng `TENANT_AUTH_CONNECTION`.

**IdP-initiated SSO:** Nếu không có AuthnRequest tương ứng, cần chính sách riêng về unsolicited response, issuer resolution, recipient/audience và cách user chọn tenant sau login. Chỉ để Spring resolve `registrationId` dựa vào một phần dữ liệu chưa tin cậy mà bỏ issuer/cert validation là lỗi nguy hiểm. Đối với ứng dụng nhạy cảm, ưu tiên SP-initiated SSO có request correlation.

## 12. Spring Security: kết hợp OIDC và SAML, bảo vệ API nhiều issuer

Một ứng dụng web có thể hỗ trợ đồng thời OIDC login và SAML2 login, và còn có Resource Server API nhận Bearer tokens. Nhưng **người dùng web** và **API machine-to-machine** có những ranh giới khác nhau; cần thiết kế filter chains rõ ràng.

### 12.1. Ví dụ web chain cùng hỗ trợ hai phương thức đăng nhập

File `src/main/java/com/example/multitenant/WebLoginSecurity.java`, nằm trong Spring Boot app có dependencies Spring Web, Spring Security, OAuth2 Client và SAML2 Service Provider:

```java
package com.example.multitenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebLoginSecurity {

    @Bean
    SecurityFilterChain webLogin(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error",
                    "/oauth2/authorization/**",
                    "/saml2/authenticate/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Cảnh báo về cấu hình này:** Đây là mẫu **tối thiểu** cho ý tưởng nhiều authentication methods; production cần giao diện chọn connection theo tenant, endpoint metadata, CSRF/session/tenant authorization, logout, quản lý error và các Spring Security filter chains khác. Đừng dùng duy nhất `anyRequest().authenticated()` cho hệ thống đa tenant rồi coi đã có tenant isolation. Khi yêu cầu đồng thời API bearer token, cần chain riêng `securityMatcher("/api/**")` được ưu tiên, như dưới đây.

Spring Security khi tự đăng ký `SecurityFilterChain` có thể làm cấu hình mặc định của Boot lùi lại; phải bật rõ `oauth2Login` và `saml2Login` trong chain xử lý các URL liên quan. Nếu tách nhiều chains, các endpoint OAuth2 redirect và SAML ACS phải thuộc chain đúng, không bị `securityMatcher` quá hẹp loại khỏi filter cần thiết.

### 12.2. Resource Server multi-tenancy: cùng từ, phạm vi kỹ thuật khác

Spring Security Resource Server có khái niệm **multi-tenancy** khi API chấp nhận Bearer tokens từ nhiều token issuers hoặc nhiều chiến lược xác thực. Ví dụ:

```java
package com.example.multitenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        JwtIssuerAuthenticationManagerResolver resolver =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://issuer-a.example.org",
                "https://issuer-b.example.org");

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }
}
```

Đây là class **Spring Security servlet**, cần `spring-boot-starter-oauth2-resource-server` và dependencies phù hợp; không phải chương trình Java 17 thuần chạy bằng `javac`. Nếu dùng cùng project với web chain `WebLoginSecurity`, thêm `@Order(2)` cho web chain hoặc đảm bảo thứ tự chains rõ; API chain chỉ xử lý `/api/**`.

**Điểm cực kỳ quan trọng:** `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` cho phép **chỉ các issuers trong danh sách tin cậy**. Nó có thể xem `iss` chưa xác minh như gợi ý để chọn AuthenticationManager, rồi decoder phải xác minh chữ ký, issuer, audience và các claims theo cấu hình tương ứng. Không lấy một `iss` bất kỳ từ token rồi tải `jwks_uri`/tạo AuthenticationManager mới mà chưa xác minh issuer thuộc allowlist; điều này tạo rủi ro issuer spoofing và SSRF.

**Nhiều issuer JWT không tự là nhiều application tenants.** Sau `oauth2ResourceServer` xác thực Bearer token, API vẫn phải kiểm tra **resource audience, scopes/authorities, local identity mapping, tenant membership và từng object**. Code mẫu chỉ xác thực, chưa cấp quyền tenant.

### 12.3. Khác biệt giữa browser login và Bearer token API

| Thuộc tính | Browser OIDC/SAML login | OAuth2 Resource Server API |
| --- | --- | --- |
| Chứng cứ | OIDC ID Token qua authorization code flow / SAML Assertion | OAuth2 Access Token (JWT hoặc opaque) |
| Session | Thường có `HttpSession`/session cookie | Thường stateless theo mỗi request Bearer |
| Nơi chọn provider | OIDC/SAML registration và login correlation | AuthenticationManager/JwtDecoder/issuer resolution |
| Cấu hình chính | `oauth2Login`, `saml2Login` | `oauth2ResourceServer` |
| Audience | OIDC ID Token audience = RP client_id; SAML = SP entityID | Access token audience phải đúng API theo issuer/resource server policy |
| Tenant isolation | Membership + object authorization sau login | Membership/tenant/object authorization sau token validation |
| Nguy cơ nhầm | Cùng email/issuer => auto-join tenant | Token issuer đúng nhưng token không dành cho API hoặc actor không thuộc tenant |

Không đưa ID Token của browser vào Authorization Bearer header rồi coi đó là access token API. Không dùng OIDC client registration làm `JwtDecoder` arbitrary cho mọi issuer; mỗi giao thức có validation và resource audience riêng.

## 13. Tenant context trong session và cách chống cross-tenant data leakage

Nếu người dùng thuộc Red và Blue, giao diện có thể cho chọn active tenant. Một phương án là lưu `activeTenantId` ở server-side session sau khi kiểm tra membership, rồi gắn tenant context cho request. Tuy vậy:

- **Đổi active tenant** là thao tác có authorization; trước khi chuyển sang Blue phải kiểm tra account ACTIVE và membership Blue ACTIVE.
- **Không dùng một ThreadLocal tenant context mà quên clear** khi xử lý thread pool; phải có lifecycle filter/interceptor an toàn và không để state rò sang request khác.
- **Không dùng activeTenantId trong session như bằng chứng vĩnh viễn** nếu quyền vừa bị thu hồi; cần phiên bản policy/recheck trên các thao tác quan trọng.
- **TenantId từ path hoặc subdomain** vẫn chỉ là requested tenant; handler phải so với active tenant/membership tùy thiết kế.
- **Không dùng tenantId client nhập trực tiếp để chọn schema/database connection** khi chưa kiểm tra mapping và authorization.
- **Cache keys** phải chứa tenant scope và quyền thích hợp; cache `report:123` không an toàn nếu tenant khác cũng có ID 123. Dùng `(tenantId, reportId, policy context)` hoặc cơ chế cache cách ly.
- **Search indexes, object storage, queues, background jobs, exports, audit logs** cũng phải mang tenant context được xác minh và kiểm tra quyền, không chỉ REST controllers.
- **Global admin** (nếu có) là policy riêng có audit/step-up, không suy từ group `Admins` do một IdP khách hàng gửi.

### 13.1. Mẫu query tenant-safe

Ví dụ repository dùng parameterized query:

```sql
SELECT id, tenant_id, title
FROM report
WHERE tenant_id = :authorizedTenantId
  AND id = :reportId;
```

`:authorizedTenantId` phải xuất phát từ service đã **xác minh user có quyền tenant đó**, không phải raw query string. Sau khi truy vấn, service còn phải xem quyền trên báo cáo cụ thể (owner, trạng thái, classification). Không sử dụng:

```sql
SELECT id, tenant_id, title
FROM report
WHERE id = :reportId;
```

cho request tenant-scoped, vì report ID có thể hợp lệ nhưng thuộc tenant khác. **Tenant-aware repository/filter không thay thế object-level authorization** khi một tenant có nhiều cấp phân quyền.

### 13.2. Cảnh báo về việc đổi tenant đồng thời ở nhiều tab

Nếu active tenant lưu trong **một HttpSession chung**, hai tab cùng origin có thể chia sẻ session cookie; đổi tenant ở tab B có thể làm tab A âm thầm chuyển ngữ cảnh. Cách giảm rủi ro:

- Đặt tenant **trong route** (ví dụ `/t/org-red/reports`) và kiểm tra quyền mỗi request, thay vì một biến session toàn cục thay đổi mà URL không thể hiện.
- Kiểm tra `tenantId` của resource và route luôn trùng.
- Với API, kiểm tra context từ token/membership server thay vì tin activeTenant session do một tab mới thay đổi.
- Nếu cần “tenant hiện hành” trong UI, coi đó là **sở thích trình bày**, không là chứng cứ cấp quyền cuối cùng.
- Test hai tab và các request song song, đặc biệt export/report background jobs.

## 14. Cấu hình onboarding và vòng đời nhiều IdP/tenant

### 14.1. Onboard tenant mới không mặc nhiên onboard IdP mới

Khi tạo tổ chức mới trong SaaS:

1. Tạo `tenantId` ổn định, trạng thái ban đầu `PENDING`, chính sách dữ liệu và owner.
2. Chọn connection IdP đang được hỗ trợ hoặc tạo yêu cầu federation mới.
3. Nếu dùng connection chung, cấu hình mapping tenant→connection và policy riêng, **không cấp membership cho mọi user của issuer đó**.
4. Nếu khách yêu cầu IdP riêng, xác minh owner/issuer/metadata/certificate/client redirect, thực hiện security review, thêm connection có trạng thái `PENDING`.
5. Kiểm thử login và quyền tenant với tài khoản test; chỉ sau QA mới đưa connection/tenant vào `ACTIVE`.
6. Xác định quy trình deprovision: khóa tenant, xóa access, bảo quản/xóa dữ liệu theo hợp đồng, không tự xóa external identity nếu user vẫn ở tenant khác.

**Đặc biệt:** Một quản trị viên tenant không nên có quyền tự nhập `metadataUrl`/`issuerUri` bất kỳ khiến backend đi fetch từ mạng nội bộ; cần allowlist/approval/egress để chặn SSRF và ngăn IdP trust poisoning.

### 14.2. Onboard IdP mới không mặc nhiên tạo tenant mới

Khi thêm một nhà cung cấp login:

1. Xác minh tổ chức sở hữu IdP và issuer/IdP entityID; xác định tin cậy bằng DNS/TLS/metadata signature theo mô hình.
2. Với OIDC, đăng ký client, callback HTTPS, xác minh discovery/JWKS từ URL được duyệt; yêu cầu exact `iss`, `aud`, state/nonce.
3. Với SAML, xác minh IdP metadata, signing certificate, SSO binding và ACS/SP entityID; test signature/audience/recipient/time/correlation.
4. Đặt `connectionId` và `registrationId` không trùng khóa đã dùng; review tác động tới current users.
5. Chỉ map connection này vào **những tenants được tổ chức chủ chấp nhận**.
6. Xác định mapping stable subject, email profile, groups và quyền; không cho nhóm đối tác `Admin` tự thành `ROLE_ADMIN`.
7. Test ở staging với resource của tenant khác và khi user chưa có membership.
8. Lập lịch certificate/JWKS rollover, metadata refresh, logout, incident response và offboarding.

## 15. Chính sách quản trị và phân quyền theo từng tenant

Một SaaS thường có ít nhất ba loại quyền:

| Quyền | Phạm vi | Ví dụ | Nguy cơ nếu nhầm |
| --- | --- | --- | --- |
| **Platform operator** | Toàn nền tảng, giới hạn rất chặt | Quản lý infrastructure/tenants | Mọi user có group `admin` từ IdP khách có thể thành superadmin |
| **Tenant administrator** | Chỉ tenant cụ thể | Quản lý member/connection Red | Admin Red có thể sửa dữ liệu/config Blue |
| **Tenant member** | Chỉ tenant và resources được cấp | Đọc báo cáo Red | Membership Red tự cho phép đọc Blue |
| **Identity provider operator** | Quản lý IdP nguồn | Thay signing cert của OP/IdP | IdP operator tự có quyền xóa tenant data |
| **Connection administrator** | Quản trị federation connection cụ thể | Cập nhật issuer/cert/callback | Nhập metadata độc hại hoặc gán connection vào tenant trái phép |

Role `TENANT_ADMIN` không đủ nếu thiếu `tenantId` tương ứng. Hãy dùng `hasAuthority` làm điều kiện cấp độ route chỉ khi scope rõ, và tiếp tục kiểm tra `(localAccountId, tenantId, operation, resource)` ở service. Quyền global admin cần policy riêng và audit mạnh.

Không dùng `ROLE_ADMIN` trong phiên người dùng như “superuser mọi tenant” nếu nhóm Admins chỉ đến từ một IdP/tenant khách; đó là con đường phổ biến dẫn tới privilege escalation.

## 16. Threat model: lỗi nhiều IdP khác lỗi nhiều tenant

| Rủi ro | Lớp gây lỗi | Ví dụ | Biện pháp |
| --- | --- | --- | --- |
| **Issuer confusion** | Authentication | Token từ issuer B được kiểm bằng trust config issuer A hoặc tin bất kỳ `iss` | Chỉ accept issuers allowlisted; verify exact issuer, signature, audience |
| **IdP trust poisoning** | Federation config | Tenant nhập metadata/JWKS URL khiến app tin khóa attacker | Approval, signed metadata/trust anchor, egress URL allowlist |
| **Account takeover qua email** | Identity linking | OP B gửi email trùng user OP A rồi auto-link account | Stable issuer+subject, verified linking/step-up, unique constraints |
| **SAML cross-SP replay** | SAML validation | Assertion cấp SP A được gửi ACS SP B | AudienceRestriction, Recipient, Destination, InResponseTo/replay |
| **Tenant spoofing** | Tenant routing | Client gửi `X-Tenant: org-blue` hoặc `?tenant=org-blue` | Xác minh tenant registry/membership; không tin headers thô |
| **BOLA/IDOR** | Resource authorization | User Red yêu cầu `/t/blue/reports/123` | Check tenant/resource ownership và permission server-side |
| **Group name collision** | Entitlement mapping | Group `Admins` ở Partner được map global `ROLE_ADMIN` | Exact source+tenant+group mapping allowlist |
| **Host header injection** | Discovery/redirect routing | Fake `X-Forwarded-Host` thay callback/tenant | Trusted proxy, canonical host, domain ownership check |
| **Cross-tab tenant leak** | Session context | Tab Red đổi tenant khi tab Blue hoạt động | Tenant-bound routes, recheck mỗi request, không dùng mutable global tenant |
| **Wrong audience for API** | OAuth2 Resource Server | ID Token được dùng làm access token hoặc token của API khác | Verify resource audience/scope; tách web login và API chain |
| **Stale membership** | Authorization lifecycle | User bị thu hồi ở Blue nhưng session giữ quyền cũ | Invalidation/recheck/policy version, revoke group changes |
| **Tenant enumeration** | UX/API | Error “org-blue exists” lộ danh sách khách | Rate limit, generic errors, least-privileged discovery |
| **Unsafe global logout** | Session/tenant | Logout Red xóa sai session của account/tenant khác | Session registry/correlation và phạm vi logout rõ |
| **Shared cache across tenant** | Data layer | Report ID 42 cache hit của tenant khác | Tenant-aware keys/isolation và object check |
| **TOCTOU membership** | Authorization concurrency | Kiểm membership rồi async job xử lý sau khi bị revoke | Propagate tenant+actor+policy version, recheck tại execution |
| **Rogue customer admin** | Governance | Admin tenant tự gán issuer hoặc cert từ tenant khác | Bounded admin roles, approval/dual control, audit |

**Mấu chốt:** Xác minh ID Token hoặc SAML assertion thành công chỉ đóng cánh cửa “người chưa xác thực”. Nó **không** đóng cánh cửa “người đã xác thực nhưng đang truy cập sai tổ chức”.

## 17. Kịch bản kiểm thử có giá trị phát hiện lỗi

### 17.1. Ma trận positive/negative

| Ca kiểm thử | Thiết lập | Kết quả phải đạt |
| --- | --- | --- |
| **One tenant, two providers** | Red cho Staff OIDC và Partner SAML; hai users có membership Red | Cả hai login đúng source, vào đúng Red theo permission riêng |
| **One provider, two tenants** | Staff OP; user có membership Red + Blue | Một principal hợp lệ có thể chọn từng tenant sau authorization |
| **Provider được phép nhưng không có membership** | Partner connection được Red cho phép; user Partner chỉ thuộc Gold | Từ chối Red, dù login Partner thành công |
| **Tenant không cho provider** | Staff user yêu cầu Gold; Gold chỉ cho Partner | Từ chối Gold |
| **Trùng subject khác issuer** | Staff `sub=u-42` và Partner `sub=u-42` | Hai external identities riêng, không merge |
| **Trùng email khác issuer** | Hai ID Tokens có email giống nhau | Không auto-link local accounts |
| **Sai issuer nhưng đúng registrationId string** | Token ký bởi issuer lạ | OIDC validation từ chối |
| **Issuer URL cùng hostname khác path** | Token `iss=/realm/other` thay `/realm/staff` | Từ chối vì issuer exact mismatch |
| **SAML IdP trả audience sai SP** | Response ký hợp lệ nhưng Audience khác SP entityID | SP từ chối |
| **SAML Recipient khác ACS** | Response ký hợp lệ, Recipient/ACS sai | SP từ chối |
| **OIDC state/nonce không khớp** | Callback từ login khác/tab sai | Spring không thiết lập login từ response không tương ứng |
| **Login callback không có tenant-intent** | SP-initiated correlation mất hoặc unsolicited SAML | Không chọn tenant bất kỳ; yêu cầu chọn/validate theo policy |
| **Tenant slug giả** | `/t/nonexistent/login` | Lỗi an toàn, không fetch IdP URL từ slug |
| **Host header giả** | `Host: blue.attacker.invalid` | Không chọn tenant mới hoặc redirect theo hostname chưa tin |
| **Đổi active tenant** | User Red+Blue chọn Blue | Kiểm membership Blue rồi tải đúng dữ liệu Blue |
| **Hai tab song song** | Tab Red và tab Blue | Request mỗi tab không rò dữ liệu do session active tenant thay đổi |
| **Cross-tenant report ID** | User Red gọi report thuộc Blue | `403` hoặc `404` theo policy, không lộ nội dung |
| **Role collision** | Partner group `Admins` | Không thành platform admin hoặc admin Red nếu không có mapping explicit |
| **Membership bị revoke** | Red bị khóa khi user vẫn có session | Request sau thu hồi phải bị từ chối theo revocation SLA |
| **IdP cert/JWKS đổi** | Corp OP rotate keys hoặc SAML IdP rotate X.509 | Chỉ trust approved keys của issuer, không mở trust cho tenants khác |
| **API bearer issuer hợp lệ, sai audience** | Access Token cho service khác | Resource Server từ chối |
| **Session logout** | Logout app web, IdP còn SSO | User có thể SSO lại, nhưng tenant quyền vẫn phải check lại |
| **Tenant bị disabled** | Tenant Red status DISABLED | Không được cấp truy cập Red ngay cả khi user authenticated |
| **SCIM provisioning** | Membership mới/cũ từ IdP sync | Chỉ cập nhật tenant tương ứng, không xóa membership của tenant khác |

**Phương pháp tạo test:** Dùng IdP test/OP test phát token/assertion hợp lệ cho positive cases và hợp lệ về chữ ký nhưng sai issuer/audience/tenant policy cho negative cases. Không sửa raw token/assertion đã ký rồi kết luận sai tenant từ lỗi chữ ký; test phải cô lập validator cần đánh giá.

### 17.2. Kiểm thử tài nguyên cụ thể

Ví dụ user Staff có `REPORT_READ` cho Red và Blue nhưng không có quyền với report secret của Blue:

```text
GET /t/red/reports/100         -> 200 nếu report thuộc Red và quyền hợp lệ
GET /t/blue/reports/200        -> 200 nếu report thuộc Blue và quyền hợp lệ
GET /t/blue/reports/299        -> 403/404 nếu object-level policy từ chối
GET /t/gold/reports/400        -> 403/404 do không có membership Gold
GET /t/red/reports/200         -> 403/404 vì report 200 thuộc Blue
```

Mã HTTP có thể khác theo chính sách che existence; điều bắt buộc là **không tiết lộ nội dung và không thực hiện thao tác trái quyền**. Không coi một HTTP 200 ở trang login là đã chứng minh được tenant authorization.

### 17.3. Kiểm thử audit log và tiêu chí riêng tư

Log nên có `eventId`, `timestamp UTC`, `protocol`, `registrationId`, `verified issuer/idpEntityId`, `localAccountId` dạng tham chiếu an toàn, `requestedTenantId`, `authorizedTenantId`, `permission`, `resourceTenantId`, `decision`, `policyVersion`, `traceId`. Giảm độ nhạy bằng pseudonymization và retention thích hợp.

Không log raw SAMLResponse, ID Token, Access Token, Refresh Token, private key, email/NameID nhạy cảm, session cookie. Không lấy issuer hoặc tenant từ **claims chưa verified** làm log label kết luận, chỉ ghi nó như input bị từ chối khi có lý do điều tra và cơ chế lọc dữ liệu.

## 18. Những lỗi thiết kế và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| “Chúng tôi có 5 IdP nên tạo 5 tenants” | Đồng nhất nguồn xác thực với organization data scope | Thiết kế tenant registry riêng, many-to-many connections |
| “Chỉ một issuer nhưng nhiều khách” | Không có phân quyền membership/resource sau login | Thiết kế tenant membership và object isolation |
| “Người dùng có email đúng domain nhưng không vào tenant” | Email chỉ là thuộc tính; chưa có membership | Thêm membership hợp lệ theo quy trình phê duyệt, không auto-join |
| Login thành công nhưng vẫn 403 ở Red | Authenticated khác authorized; membership/role Red thiếu | Kiểm account, tenant, connection policy và permission |
| SAML SSO thành công nhưng vào nhầm Blue | Không lưu tenant-intent hoặc resolve registration/active tenant sai | Bảo vệ request correlation, check membership sau login |
| Một user ở Red và Blue bị đổi thông tin khi chuyển | Tenant context mutable/global trong HttpSession | Tenant in route, immutable request context và per-request authorization |
| Token OIDC của OP B được hệ thống chấp nhận như OP A | Issuer/keys/audience validation sai | Bind decoder/token validation với trusted registration và exact issuer |
| API chấp nhận Bearer từ mọi `iss` | Dynamic decoder từ untrusted issuer | Trusted issuers allowlist, tách API audience validation |
| SAML assertion cấp SP A được SP B chấp nhận | Thiếu audience/recipient/correlation validation | Dùng Spring/OpenSAML; cấu hình entityID và ACS đúng |
| User bị thu hồi khỏi tenant nhưng vẫn truy cập | Session authority/cache cũ hoặc policy version không đổi | Invalidate/recheck membership, revoke session theo SLA |
| Một tenant thấy dữ liệu tenant khác | Query thiếu tenant predicate, cache key không phân tenant, background job mất context | Bổ sung scope ở data layer và object authorization |
| Onboarding IdP mới làm app truy cập nội bộ | Nhận metadata URI tùy ý, follow redirect/SSRF | Approve source URI, egress allowlist, metadata signature |
| IdP của cùng thương hiệu có nhiều issuers | So issuer chỉ theo hostname/provider brand | So exact `iss` bao gồm path/realm/tenant đã phê duyệt |
| Logout một app vẫn đăng nhập lại | IdP SSO session còn; app local session mới được tạo | Phân biệt local logout và federated logout; kiểm quyền tenant lại |
| Registration ID trùng hoặc không tìm được | Nhầm `tenantId` với `registrationId` hoặc file config thiếu | Đặt namespace rõ, kiểm `ClientRegistrationRepository`/`RelyingPartyRegistrationRepository` |
| Admin của tenant Red trở thành admin mọi tenant | Map IdP group Admin → `ROLE_ADMIN` không giới hạn scope | Map `(issuer,group,tenant)` sang permission riêng và kiểm resources |

**Trình tự debug đề xuất:**

```text
1. Request đang xin dùng tenantId nào, tenant ấy có ACTIVE không?
2. Browser login dùng connection/registrationId nào? Có được tenant cho phép?
3. SAML/OIDC được Spring xác minh với issuer, key, audience, state?
4. External identity -> localAccountId nào, có bị link nhầm email?
5. Membership của account ở requested tenant có ACTIVE không?
6. Quyền trong tenant có đủ cho action không?
7. Tài nguyên thực tế thuộc tenant nào? Data/cache/search scope có đúng?
8. Session/correlation/Host/proxy/async context có làm đổi tenant không?
9. Nếu vẫn lỗi, xem audit policyVersion, IdP metadata/key, distributed cache.
```

## 19. Checklist kiến trúc và vận hành

- [ ] Thuật ngữ `IdP/OP`, `issuer`, `provider`, `registrationId` và `application tenantId` được định nghĩa riêng.
- [ ] Hệ thống có `Tenant Registry` và `Identity Provider/Connection Registry` tách biệt, có bảng `TenantAuthConnection` many-to-many.
- [ ] Một tenant có thể dùng nhiều IdP và một IdP có thể phục vụ nhiều tenants, theo chính sách rõ ràng.
- [ ] OIDC validation kiểm `iss`/`aud`/signature/`exp`/`state`/`nonce` đúng flow; SAML validation kiểm issuer/signature/audience/recipient/time/`InResponseTo`.
- [ ] Không sử dụng `email`, domain email, displayName, raw `sub` hoặc `NameID transient` để auto-link giữa IdP.
- [ ] External identity keys có issuer/tenant qualifiers phù hợp; localAccountId do ứng dụng cấp.
- [ ] Đăng nhập từ tenant cụ thể lưu intent/correlation chống sửa; sau login **luôn** kiểm membership và provider policy.
- [ ] Không dùng raw Host/`X-Forwarded-Host`, path/query/RelayState/JWT chưa verify làm authority tạo tenant hoặc IdP trust.
- [ ] Dùng registration-per-tenant chỉ khi có nhu cầu trust/client/ACS riêng; không suy registration count = tenant count.
- [ ] Group/role mapping giới hạn theo issuer/tenant/group ID; không tin `ROLE_ADMIN` của IdP khách.
- [ ] Phân quyền tài nguyên có `tenant_id` và kiểm object-level; queries/cache/search/jobs/audit đều tenant-aware.
- [ ] Resource Server multi-issuer chỉ cho các issuers tin cậy và verify resource audience; không nhầm ID Token với Access Token.
- [ ] Session/active tenant trong nhiều tab được kiểm thử; membership revocation có SLA.
- [ ] Khách hàng quản trị connection được giới hạn quyền; thay issuer/cert/metadata URI có change approval, review và audit.
- [ ] Onboarding/offboarding tenant khác onboarding/offboarding IdP; không xóa identity/dữ liệu của tổ chức khác.
- [ ] Test cả mô hình one-to-many, many-to-one, many-to-many và các ca cross-tenant/unknown issuer/email collision.
- [ ] Có giám sát issuance keys, metadata/JWKS rollover, session logout và tenant authorization failures.
- [ ] Logging không lưu token/assertion/cookie/secrets/PII không cần thiết.

**Kết luận:** **Nhiều nhà cung cấp** là vấn đề **federated authentication**: ứng dụng phải biết *nguồn nào đáng tin, cách xác minh bằng chứng từ nguồn đó và danh tính ổn định là ai*. **Nhiều tenant** là vấn đề **tổ chức, dữ liệu và phân quyền**: ứng dụng phải biết *người đã xác thực thuộc những tổ chức nào, có thể làm gì trên tài nguyên nào*. Một thiết kế đúng dùng **hai registry khác nhau và một bảng kết nối nhiều–nhiều**, liên kết external identity vào local account có kiểm soát, kiểm membership sau authentication và enforce tenant ở **mỗi điểm truy cập dữ liệu**. Không thay thế bất kỳ bước nào chỉ bằng tên IdP, issuer, email domain hoặc registrationId.

## 20. Tài liệu tham khảo

1. [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) — `ClientRegistration`, `ClientRegistrationRepository`, `registrationId` và cấu hình nhiều providers.
2. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — authorization request resolver, user authorities mapping và custom login logic.
3. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — multi-tenant `RelyingPartyRegistrationRepository`, AuthnRequest/ACS, `registrationId` và metadata.
4. [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html) — `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` và chính sách trusted issuers.
5. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — URL authorization và lớp quyền sau authentication.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `iss+sub`, subject pairwise, ID Token `aud`, state/nonce, giới hạn email.
7. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html) — issuer metadata và exact issuer verification.
8. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — `Issuer`, `AudienceRestriction`, `SubjectConfirmation`, NameID và signatures.
9. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — IdP/SP `entityID`, ACS và relying-party metadata.
10. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, object-level authorization, least privilege.
11. [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) — nguy cơ IDOR/BOLA cross-tenant.
12. [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — hạn chế dynamic issuer/metadata fetch và egress.
