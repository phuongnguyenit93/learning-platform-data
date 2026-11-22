# Vai trò LDAP và Active Directory làm nguồn danh tính phía sau IdP

Trong kiến trúc đăng nhập liên kết, **LDAP/Active Directory** thường là **nguồn hồ sơ và trạng thái tài khoản** mà **Identity Provider (IdP)** sử dụng. **IdP** mới là bên tổ chức phiên SSO, xác minh credentials theo cơ chế phù hợp, áp MFA, ánh xạ thông tin và phát hành **OIDC ID Token, SAML Assertion hoặc CAS Service Ticket**. Ứng dụng **Spring Security** tin IdP theo giao thức federation được cấu hình; nó không nên hiểu một kết quả tìm kiếm LDAP là bằng chứng người dùng đã đăng nhập.

Ví dụ tổng quan:

~~~text
Employee Browser
   -> Spring Portal (OIDC RP / SAML SP)
   -> Corporate IdP (Keycloak, AD FS hoặc giải pháp IAM)
        -> LDAP/Active Directory: account, groups, attributes, status
        -> IdP: authentication policy, MFA, session, claims
   -> Spring: protocol validation, local user linking, role/tenant
   -> Reports API / business resource
~~~

**Điểm cốt lõi:** LDAP/AD trả lời “thư mục biết gì về identity này và có thể kiểm credential theo cơ chế nào?”, IdP trả lời “phiên đăng nhập đã được chứng minh bằng cách nào và tôi cho phép phát những claims gì?”, Spring Security trả lời “issuer này đáng tin không và user có được làm thao tác này không?”. Ba trách nhiệm liên quan nhưng **không đồng nhất**.

Bài thuộc nhóm **Thư mục và tài khoản** trong module **Spring Security - federation**. Nội dung đi từ mô hình directory, LDAP bind/search, AD specifics, Keycloak User Federation, stable IDs, group mapping, account lifecycle, LDAPS/StartTLS, cấu hình OIDC trong Spring, code Java 17 chạy độc lập và kiểm thử thực tế. Miền `.example` chỉ dùng minh họa.

## 1. Phân vai: directory, IdP và application

| Thành phần | Chịu trách nhiệm | Không tự chứng minh |
| --- | --- | --- |
| **LDAP server** | Truy vấn/bind/cập nhật LDAP entries | OIDC/SAML federation token hợp lệ |
| **Active Directory Domain Services** | Directory users/groups, domain/account policies, Kerberos | Spring application role |
| **IdP** | Login, MFA, SSO session, token/assertion, claim release | Quyền business cho mọi ứng dụng |
| **Identity broker** | Xác thực upstream IdP, phát identity theo issuer mới | Mọi upstream claims đều đáng tin |
| **Spring Security RP/SP** | Xác minh issuer, audience, signature và protocol state, tạo Authentication | Password AD đã được app tự kiểm |
| **Local application** | Tenant, entitlement, roles, object authorization | Quyền admin suy từ AD Domain Admins |
| **IAM/HR/data owner** | Source of truth, schema và offboarding | Tự động thu hồi mọi token/session ngay tức thì |

Một tổ chức có 30 ứng dụng sẽ giảm rủi ro khi **tập trung LDAP bind credentials và directory schema tại IdP**, thay vì 30 apps đều kết nối trực tiếp DCs. Tuy nhiên IdP là một ranh giới tin cậy trọng yếu, cần HA, kiểm chứng thư, bảo mật secrets và vận hành cẩn thận.

## 2. Đăng nhập liên kết có LDAP/AD phía sau

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Portal
    participant IDP as Enterprise IdP
    participant AD as LDAP/Active Directory
    U->>SP: GET /reports
    SP-->>U: Redirect OIDC Authorization Request
    U->>IDP: Login hoặc IdP SSO session
    IDP->>AD: LDAP search user/status/groups khi cần
    AD-->>IDP: Directory identity/attributes
    opt Chọn password validation qua directory
        IDP->>AD: User bind hoặc credential verification an toàn
        AD-->>IDP: Success hoặc deny
    end
    IDP->>IDP: MFA + session + protocol claim policy
    IDP-->>U: Authorization code redirect
    U->>SP: OIDC callback
    SP->>IDP: Exchange code qua HTTPS
    IDP-->>SP: Tokens
    SP->>SP: Verify ID Token, issuer, audience, nonce/state
    SP->>SP: Local user, role và tenant
    SP-->>U: Application session
~~~

Đây là ví dụ **OIDC Authorization Code flow**. Trong SAML, IdP phát Assertion về ACS; trong CAS, IdP/CAS phát Service Ticket và ứng dụng validate ticket. **Không phải tất cả IdPs gửi mật khẩu qua LDAP**: có thể dùng Kerberos/SPNEGO, passkey, client certificate, delegated upstream login hoặc SSO session đã tồn tại.

Một lời giải thích kỹ thuật nên xác định chính xác bước nào **thực sự chứng minh credential** và bước nào **chỉ đọc user profile**.

## 3. LDAP là giao thức, AD là một hệ thống directory

LDAP v3 cho phép client thực hiện **Bind**, **Search**, **Compare**, **Modify** và controls theo directory schema. Hệ thống cung cấp LDAP có thể là OpenLDAP, 389 Directory Server hoặc AD DS; schemas khác nhau.

Active Directory Domain Services còn có:

- **Domain Controller (DC)**, domain/forest/OU và directory replication.
- **Global Catalog (GC)** giúp tìm kiếm trên nhiều domains với partial attribute set.
- **Kerberos KDC**, service principals, Windows account/group policies.
- Các attributes `sAMAccountName`, `userPrincipalName`, `objectGUID`, `objectSid`, `memberOf`, `userAccountControl`.
- Password expiration, lockout và trạng thái disabled được định nghĩa bởi AD policies.

**Không đồng nhất AD DS với Microsoft Entra ID.** Entra ID là cloud identity platform; nếu doanh nghiệp đồng bộ user AD lên Entra thì ứng dụng dùng OIDC của Entra không có nghĩa nó đang kết nối LDAP trực tiếp đến Entra.

## 4. Cây LDAP và Directory Entry

Ví dụ một DN:

~~~ldif
dn: CN=Lan Nguyen,OU=Employees,DC=corp,DC=example
objectClass: person
objectClass: organizationalPerson
objectClass: user
cn: Lan Nguyen
displayName: Lan Nguyen
sAMAccountName: lnguyen
userPrincipalName: lan.nguyen@corp.example
mail: lan.nguyen@corp.example
department: Finance
memberOf: CN=ReportReaders,OU=Groups,DC=corp,DC=example
~~~

Đây là **LDIF minh họa subset fields**. AD objectGUID/objectSid thường có representation binary riêng; bản LDIF không liệt kê tất cả mandatory attributes.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| DN | Đường định vị đối tượng trong cây | `CN=Lan Nguyen,OU=Employees,DC=corp,DC=example` |
| RDN | Phần tên ở ngay vị trí entry | `CN=Lan Nguyen` |
| Base DN | Gốc phạm vi LDAP search | `OU=Employees,DC=corp,DC=example` |
| Scope | Base/one-level/subtree | Chỉ Employees subtree |
| LDAP filter | Điều kiện tìm entries | `(sAMAccountName=lnguyen)` |
| Entry UUID | ID của object từ directory | AD `objectGUID` |
| Attributes | Hồ sơ và metadata | `mail`, `displayName`, `memberOf` |

### Search không phải authentication

LDAP `search` chỉ cho biết entry có tồn tại và attributes được phép đọc. Ví dụ server tìm ra một user có email `lan@corp.example` **không có nghĩa request xuất phát từ Lan**. Xác thực phải có user bind, Kerberos, IdP signed assertion hoặc cơ chế authentication tương ứng.

Ba kết quả search phải được phân biệt: **0 user** → deny; **1 user** → vẫn cần credential validation/status check; **nhiều users** → deny do không unique, không chọn bản đầu tiên để login. Search filters phải được giới hạn và chống injection.

## 5. Service bind so với user bind

Một IdP LDAP connector thường thực hiện:

~~~text
1. Service account bind với quyền READ hạn chế
2. Search user DN theo username đúng schema/OU
3. Kiểm uniqueness, account enabled và login restrictions
4. Nếu là password flow: bind/credential validation cho user
5. Áp MFA, risk-based authentication, IdP session
6. Phát identity cho ứng dụng đã đăng ký
~~~

**Service bind** dùng một account hệ thống để **tìm kiếm**, không chứng minh người dùng đã đăng nhập. **User bind** dùng credential của user để chứng thực với LDAP/AD theo chính sách.

Một số IdPs dùng **Kerberos/SPNEGO** xác minh user rồi LDAP chỉ đọc profile/groups; không có bước user password bind. Vì vậy cụm “IdP dùng AD” cần được làm rõ: **AD password authentication**, **Kerberos SSO** hay **directory lookup**.

Spring Security LDAP reference giải thích `LdapBindAuthenticationManagerFactory` dùng LDAP server kiểm password, không dùng `UserDetailsService` để đọc hash password rồi tự so. Không cấp app/IdP quyền đọc password hash chỉ để “tự xác thực”.

## 6. Keycloak User Federation: AD/LDAP là nguồn sau IdP

Keycloak có **User Federation → Add LDAP providers**. Cấu hình phổ biến:

| Property/khái niệm | Ví dụ hoặc quyết định |
| --- | --- |
| Vendor | Active Directory hoặc LDAP vendor tương ứng |
| Connection URL | `ldaps://dc01.corp.example:636` |
| Bind DN | `CN=svc-ldap-read,OU=Service Accounts,DC=corp,DC=example` |
| Bind Credential | Secret do vault/secret manager quản lý |
| Users DN | `OU=Employees,DC=corp,DC=example` |
| Username LDAP attribute | `sAMAccountName` hoặc `uid` theo schema |
| RDN LDAP attribute | Field cho relative DN |
| UUID LDAP attribute | `objectGUID` đối với AD, `entryUUID` ở nhiều LDAP servers |
| User Object Classes | Chọn user entries, tránh computers/services ngoài scope |
| Search Scope/User LDAP Filter | Giới hạn entry candidates |
| Import Users | Import/copy profile hay đọc LDAP trực tiếp |
| Edit Mode | `READ_ONLY`, `WRITABLE`, `UNSYNCED` |
| Mappers | Attributes, groups, identity linking |
| Sync Settings | Full sync/changed users sync |

Tên fields và hành vi có thể thay đổi theo **Keycloak version** và mapper configuration, cần đối chiếu docs của bản đang triển khai.

### Import Users có sao chép password AD không?

**Không.** Keycloak Server Administration Guide nêu khi Import Users được bật, Keycloak có thể import/copy **user profile** vào local DB và sync on-demand/periodic; **password không được import** và password verification vẫn thực hiện bằng LDAP/AD provider.

Điều này không có nghĩa mọi ứng dụng đang offline vẫn có thể login. LDAP down, cache stale và IdP session tồn tại có thể ảnh hưởng khác nhau tùy flow. **Không tự coi LDAP cache là password authority**.

### READ_ONLY, WRITABLE và UNSYNCED

| Mode | Hành vi | Cẩn trọng |
| --- | --- | --- |
| `READ_ONLY` | Mapped user attributes không được IdP ghi ngược LDAP | Nên cân nhắc khi AD authoritative |
| `WRITABLE` | Có thể cập nhật mapped fields/password theo quyền LDAP | Cần ACL, audit, ownership, write policy |
| `UNSYNCED` | Thay đổi được giữ ở IdP local store thay vì LDAP | Có thể có hai nguồn truth cho cùng field |

**Thay Edit Mode hoặc Import Users về sau không nhất thiết tự cập nhật mappers đã tạo.** Keycloak ghi rõ một số mapper configs được xây từ giá trị tại lúc tạo provider; migration phải kiểm từng mapper, không chỉ thay dropdown.

### User synchronization và caching

- **On-demand**: lookup/import khi user login hoặc query lần đầu.
- **Full sync**: duyệt users trong scope, cần kiểm tải DC/LDAP và pagination.
- **Changed users sync**: chỉ xử lý những users thay đổi theo tracker của provider, giảm tải nhưng không mặc định xử lý mọi deletion/role revocation tức thì.
- **Mapper direct LDAP read**: một số fields có thể đọc trực tiếp thay vì DB cache.
- **Group membership**: có thể dùng strategy/sync riêng.

Keycloak khuyến nghị sync toàn bộ lần đầu rồi đặt định kỳ changed-users sync khi phù hợp. **Sync interval, replication lag, IdP sessions, token TTL và Spring sessions là các tầng khác nhau**, không được tự tuyên bố thay group trong AD có hiệu lực ngay trên mọi browser.

## 7. Nguồn định danh bền vững: đừng gộp người theo email

| Identifier | Vai trò | Ổn định/giới hạn |
| --- | --- | --- |
| AD `objectGUID` | Identity của một AD object | Giữ qua rename/move trong forest; delete/recreate sẽ có object mới |
| LDAP `entryUUID` | Entry ID nơi server hỗ trợ | Scope theo directory/provider và replication |
| DN | Định vị entry | Có thể đổi khi đổi OU/CN |
| `sAMAccountName` | Domain-scoped legacy login | Đổi/reuse hoặc trùng domain khác |
| `userPrincipalName` | Username dạng UPN | Có thể đổi suffix/tên; không đồng nhất email |
| `mail` | Contact attribute | Mutable, có thể trùng/shared/recycled |
| `objectSid` | Windows security principal | SIDHistory và migration semantics riêng |
| OIDC `sub` | Subject identifier của IdP | Liên kết với `iss`; không mặc nhiên bằng objectGUID |
| OIDC `iss` | Issuer mà RP tin | Phải verify với token/metadata |
| `preferred_username` | Username hiển thị | Không mặc định immutable |

**Microsoft xác nhận objectGUID của AD object không đổi khi rename hoặc move**, còn DN có thể thay đổi. Tuy vậy GUID không phải phép màu giữ qua xóa/tạo mới, directory migration hoặc khác forests.

Một liên kết an toàn hai tầng:

~~~text
Directory -> IdP:
  (LDAP provider ID, objectGUID) -> IdP internal user

IdP -> Spring:
  (verified issuer, OIDC sub) -> local user ID + tenant
~~~

**Không thay `sub` bằng email** khi link account. Nếu issuer đổi sau IdP migration, cần quy trình relink identity được phê duyệt, không tự gộp dựa vào username/UPN.

### objectGUID binary và Keycloak decoder

AD `objectGUID` thường được trả qua LDAP dưới dạng **16 binary bytes**, không phải plain text UUID string. Keycloak Upgrading Guide 26.x có thay đổi về **Decode Binary Attribute As** và tùy chọn base64/uuid cho LDAP mappers.

Kiểm khi upgrade: giá trị raw ID, decoded string, linked user, group mapper và SSO subject trước/sau migration. Không “fix” duplicate user bằng cách tự xóa bản ghi IdP nếu mapper đã đổi representation.

### Nhiều LDAP servers và failover

Nếu cùng một LDAP provider có nhiều URLs, chúng phải là **replicas của cùng directory** với cùng object UUID cho một user. Hai directories độc lập dù dữ liệu tên/email giống nhau có thể sinh objectGUID/entryUUID khác. Keycloak docs cảnh báo cấu hình đó có thể gây duplicate hoặc failure khi failover. Mỗi nguồn độc lập cần provider hoặc kiến trúc identity linking rõ.

## 8. Attributes LDAP → IdP profile → protocol claims

Ví dụ dữ liệu nguồn:

~~~text
LDAP AD:
  sAMAccountName = lnguyen
  mail = lan@corp.example
  displayName = Lan Nguyen
  givenName = Lan
  sn = Nguyen
  department = Finance
  memberOf = [ReportReaders, Employees, OtherGroups]
  userAccountControl = account status flags
  objectGUID = stable source object ID
~~~

Mapping IdP user model có thể là:

~~~text
Keycloak user:
  username = lnguyen
  email = lan@corp.example
  firstName = Lan
  lastName = Nguyen
  internal federation link -> objectGUID + provider
~~~

Và chỉ phát claims cần thiết:

~~~json
{
  "iss": "https://login.corp.example/realms/staff",
  "sub": "a7f7b22b-cf08-42db-96b2-4ba671ca35a5",
  "aud": "reports-web",
  "name": "Lan Nguyen",
  "email": "lan@corp.example"
}
~~~

**JSON là claim subset minh họa**, không phải ID Token hoàn chỉnh/có chữ ký; trong sản phẩm thật Spring kiểm signature, `iss`, `aud`, `exp`, nonce/state và protocol flow đúng.

| LDAP/AD field | IdP mapping | Có nên phát cho ứng dụng? |
| --- | --- | --- |
| `mail` | email | Khi thật cần, theo privacy contract |
| `givenName`/`sn` | firstName/lastName | Khi cần hiển thị |
| `displayName` | name | Dữ liệu hiển thị, không ID key |
| `objectGUID` | Stable internal user link | Thường không cần phát raw GUID |
| `department` | Custom profile attribute | Chỉ client cần và được duyệt |
| `memberOf` | Group/role mapper | Giới hạn app-specific role claims |
| `userAccountControl` | Account status input | Không phát raw internal flags cho mọi RP |

**Email verified:** LDAP có `mail` không tự chứng minh chủ sở hữu hiện tại đã xác minh email. Chỉ đặt `email_verified=true` khi IdP có nguồn/trust contract và quy trình xác minh phù hợp. Không tự account-link quyền cao dựa vào một email không đáng tin.

## 9. Active Directory groups, nested membership và app roles

Ví dụ:

~~~text
User Lan
  direct group: FinanceAnalysts
FinanceAnalysts
  is member of ReportReaders
Domain Admins
  is unrelated to Reports Portal app role
~~~

`memberOf` của user thường là **direct groups**, có trường hợp nested/primary group không xuất hiện trong một danh sách đọc đơn giản. AD có `LDAP_MATCHING_RULE_IN_CHAIN` (OID `1.2.840.113556.1.4.1941`) cho truy vấn DN ancestry trên các attributes phù hợp:

~~~ldap
(&(objectCategory=person)(objectClass=user)(memberOf:1.2.840.113556.1.4.1941:=CN=ReportReaders,OU=Groups,DC=corp,DC=example))
~~~

Đây là **extension của Microsoft AD**, không phải filter portable cho mọi LDAP servers. Với cấu trúc nhiều OU/group nesting, query có thể tốn tải; cân nhắc search scope, paging, cache, group retrieval strategy, Global Catalog partial attributes và tests.

AD còn có `tokenGroups` (SID-based), group types, `primaryGroupID`, cross-domain groups và distribution groups. **Không biến mọi membership thành `GrantedAuthority`.**

Một mapping tốt:

~~~text
AD group approved for Reports:
  CN=ReportReaders,OU=Groups,DC=corp,DC=example

IdP claim for reports-web:
  roles = ["report_viewer"]

Spring local authorities:
  ROLE_REPORT_VIEWER only after issuer/token validation and local policy

AD Domain Admins:
  does NOT imply ROLE_ADMIN in Reports Portal
~~~

**Domain Admins là quyền hạ tầng, không phải mọi quyền business.** Đặt allowlist group/role theo application/tenant, data owner và review định kỳ; không dùng regex tên group chứa “admin”.

## 10. Disabled, locked và expired accounts

LDAP Search vẫn có thể trả user đã disabled; do đó **đã tìm được user không chứng minh tài khoản hoạt động**.

Trong AD:
- `userAccountControl` chứa bit **ACCOUNTDISABLE = 0x0002**.
- Lockout, password expiration, accountExpires và logon restrictions có thể phụ thuộc các attributes/tính toán khác như `msDS-User-Account-Control-Computed`.
- LDAP user bind có thể từ chối credential theo directory policy, nhưng IdP session được phát trước đó có thể còn.
- Spring local HTTP session hoặc JWT có lifetime riêng.

Ví dụ filter AD-specific loại disabled accounts:

~~~ldap
(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))
~~~

`1.2.840.113556.1.4.803` là AD bitwise AND matching rule. **Đây chỉ là điều kiện search**, không thay một chính sách full account status/MFA/revocation.

Vòng đời giả định:

~~~text
09:00 HR quyết định thôi việc
09:01 AD disables account
09:02 IdP LDAP cache có thể còn dữ liệu cũ
09:05 Existing OIDC token có thể vẫn chưa hết hạn
09:10 Changed-users sync có thể mới chạy
09:15 Spring web session có thể vẫn sống
~~~

Các mốc **không phải mặc định**. Phải đo **deprovisioning SLA**: thời gian tối đa từ khi directory disable/thu hồi group đến khi Spring endpoints từ chối. Các giải pháp tùy kiến trúc gồm token TTL, revocation/introspection, IdP session termination, back-channel logout, policy check tại resource server, event-driven SCIM/provisioning hoặc local active-account lookup.

## 11. LDAPS/STARTTLS và LDAP signing/channel binding

IdP kết nối AD trên các cổng thường dùng:

| Endpoint | Port | Lưu ý |
| --- | --- | --- |
| LDAP | TCP 389 | Có thể STARTTLS hoặc SASL; **không simple bind plaintext** |
| LDAPS | TCP 636 | TLS bắt đầu trước LDAP operations |
| Global Catalog LDAP | TCP 3268 | Forest search, partial attribute set, không TLS mặc định |
| Global Catalog LDAPS | TCP 3269 | GC qua TLS |
| Kerberos | UDP/TCP 88 | Khi flow dùng Kerberos/Windows SSO |
| DNS | TCP/UDP 53 | DC/KDC/hostname discovery |

**LDAPS khác HTTPS**: đều dùng TLS nhưng LDAP bên trong không phải HTTP.

IdP phải kiểm:
1. CA/PKIX certificate chain Domain Controller.
2. **Hostname SAN/FQDN** khớp DC mà connector gọi.
3. Certificate validity và security algorithms.
4. Bind credentials không xuất hiện trên plaintext connection.
5. Server failover và DNS routing tới endpoint đã tin.

**Không dùng trust-all X509TrustManager, hostname verification bypass hay `TLS_REQCERT never`** để chữa lỗi PKIX. Hãy sửa CA chain/certificate SAN/truststore qua đội PKI.

Microsoft phân biệt các lớp:
- **LDAP signing:** integrity/authenticity của SASL LDAP session khi cấu hình, nhất là không TLS.
- **SASL sealing:** confidentiality/integrity cho SASL phù hợp.
- **TLS LDAPS/STARTTLS:** confidentiality/integrity và server identity cho LDAP.
- **Channel Binding Token (CBT):** ràng buộc SASL authentication với TLS session, giúp giảm relay ở các cơ chế liên quan.

**Simple bind over TLS không tự dùng SASL channel binding như Kerberos SASL bind.** Với AD signing/CBT policies mới, kiểm compatibility của IdP LDAP connector/bind mechanism, không hạ security policy để “có thể đăng nhập”.

## 12. Service bind account, secrets và permission scope

Ví dụ một account IdP để search:

~~~text
DN:
  CN=svc-ldap-reader,OU=Service Accounts,DC=corp,DC=example

Allowed:
  read specific user profiles/groups under approved OUs

Forbidden:
  Domain Admin
  create/delete users
  modify security groups
  read password material
  blanket write rights
~~~

Cần:
- Giữ bind password trong secret manager/IdP credential store, không commit Git hoặc log.
- Rotate credentials có rollout đồng bộ, audit và owner.
- Giới hạn OUs, attributes, group search rights, timeout và result size.
- Giám sát bind failures/expiry/lockout.
- Không dùng AD administrator account để chữa `LDAP error 50 insufficientAccessRights`; cấp đúng read ACL nếu thật sự cần.
- Tách service bind credential và user login credential.
- Không phơi ra username enumeration hay raw directory entries trong client-visible errors.

**Quyền đọc directory không tự là quyền phát dữ liệu cho ứng dụng**: IdP phải áp claim/attribute release policy cho từng client.

## 13. Spring Security làm OIDC RP, không tự đi bind LDAP

Spring Boot OIDC client ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-oidc:
            provider: corp-idp
            client-id: reports-web
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-idp:
            issuer-uri: "https://login.corp.example/realms/staff"
~~~

`issuer-uri` chỉ **OIDC issuer** chứ không phải `ldaps://dc01...`. Spring kiểm metadata/discovery, Authorization Code callback, state/nonce, chữ ký/issuer/audience của ID Token theo flow được hỗ trợ. LDAP connector/Bind DN thuộc phạm vi của IdP.

Spring JavaConfig minh họa (cần Spring dependencies; không phải Java độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CorporateOidcSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/reports/**").authenticated()
                        .anyRequest().denyAll())
                .oauth2Login(login -> {})
                .build();
    }
}
~~~

Mẫu chỉ xác định authenticated user; **business roles và tenant/object authorization vẫn phải thêm theo thiết kế**. Map group/role claims đã verify sang `GrantedAuthority` có allowlist, không lấy raw `memberOf` trực tiếp từ browser. Với API resource server dùng bearer token, `oauth2ResourceServer().jwt()`/`JwtAuthenticationConverter` có vai trò khác OIDC browser login.

### Direct LDAP login là con đường khác

Spring Security có module `spring-security-ldap` với `LdapBindAuthenticationManagerFactory` dùng khi **Spring chính là bên nhận username/password**, ví dụ:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

AuthenticationManager directLdapManager(
        BaseLdapPathContextSource source) {
    LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(source);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
~~~

Đoạn này là **fragment trong Spring project**, không phải mẫu OIDC federation. Với AD có thể dùng `sAMAccountName`/UPN và `ActiveDirectoryLdapAuthenticationProvider` theo version. Không copy `uid` mà chưa kiểm schema. Nếu đã dùng IdP, không đặt LDAP password check ở callback OIDC để “tăng an toàn”; nó có thể phá federation và đòi credential không cần thiết.

## 14. Java JNDI LDAP search phải chống injection

Một LDAP filter ghép trực tiếp raw user input là rủi ro:

~~~text
WRONG:
  "(&(objectClass=user)(sAMAccountName=" + userInput + "))"
~~~

Một input chứa dấu `*`, `(`, `)`, `\` hoặc NUL có thể thay ý nghĩa filter. Dùng **JNDI parameterized filter** hoặc escape đúng RFC 4515. Đây là fragment Java/JNDI chạy khi có variables/environment và LDAP thật; không có stdout cố định:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.*;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://dc01.corp.example:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL, bindDn);
env.put(Context.SECURITY_CREDENTIALS, bindSecret);
env.put("com.sun.jndi.ldap.connect.timeout", "5000");
env.put("com.sun.jndi.ldap.read.timeout", "5000");

DirContext directory = new InitialDirContext(env);
try {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setCountLimit(2);
    controls.setReturningAttributes(
            new String[]{"mail", "displayName", "objectGUID"});
    String filter =
            "(&(objectCategory=person)(objectClass=user)(sAMAccountName={0}))";
    NamingEnumeration<SearchResult> results = directory.search(
            "OU=Employees,DC=corp,DC=example",
            filter,
            new Object[]{userInput},
            controls);
    try {
        while (results.hasMore()) {
            SearchResult entry = results.next();
            // Chỉ dùng được fields trong data contract.
        }
    } finally {
        results.close();
    }
} finally {
    directory.close();
}
~~~

`bindDn`, `bindSecret`, `userInput` là variables mà project thật phải cung cấp, không phải hardcoded secrets. `{0}` được JNDI substitutor xử lý thay vì chèn raw text. Search result vẫn **không chứng minh user đã authenticate**, và `objectGUID` có thể là binary cần decode đúng. TLS validation/connection pooling/failover/timeout/ACL cần triển khai thực tế.

## 15. Java 17 độc lập: ổn định identity link và app role

Chương trình Java thuần này mô phỏng **directory identity**, rename email/login, IdP issuer và local role mapping. Nó **không có** LDAP server, OIDC signature, AD group mapper, TLS hoặc actual user authentication; boolean `fresh` biểu thị giả định đã có cơ chế kiểm directory status, **không được hardcode true trong production**.

Tạo file **`DirectoryBehindIdpDemo.java`**:

~~~java
import java.util.Set;
import java.util.TreeSet;

public class DirectoryBehindIdpDemo {

    record DirectoryUser(
            String objectGuid, String login, String email,
            boolean active, Set<String> groups) {}

    static final String TRUSTED_ISSUER =
            "https://login.corp.example/realms/staff";

    static String identityKey(String issuer, DirectoryUser user) {
        return issuer + "|" + user.objectGuid();
    }

    static Set<String> roles(DirectoryUser user) {
        Set<String> result = new TreeSet<>();
        if (user.groups().contains("APP_REPORT_READERS")) {
            result.add("ROLE_REPORT_VIEWER");
        }
        return result;
    }

    static String authorize(
            String issuer, DirectoryUser user, boolean fresh) {
        if (!TRUSTED_ISSUER.equals(issuer)) {
            return "DENY: untrusted issuer";
        }
        if (!fresh) {
            return "DENY: stale directory state";
        }
        if (!user.active()) {
            return "DENY: disabled directory account";
        }
        if (!roles(user).contains("ROLE_REPORT_VIEWER")) {
            return "DENY: missing application grant";
        }
        return "ALLOW: ROLE_REPORT_VIEWER";
    }

    public static void main(String[] args) {
        String guid = "75b43cc2-21d9-4ce5-a9c5-d6d3bf08fa20";

        DirectoryUser user = new DirectoryUser(
                guid, "lnguyen", "lan@corp.example", true,
                Set.of("APP_REPORT_READERS", "Domain Admins"));

        DirectoryUser renamed = new DirectoryUser(
                guid, "lan2", "lan.new@corp.example", true,
                user.groups());

        DirectoryUser disabled = new DirectoryUser(
                guid, "lan2", "lan.new@corp.example", false,
                user.groups());

        DirectoryUser noGrant = new DirectoryUser(
                guid, "lnguyen", "lan@corp.example", true,
                Set.of("Domain Admins"));

        System.out.println("Stable link: "
                + identityKey(TRUSTED_ISSUER, user).equals(
                    identityKey(TRUSTED_ISSUER, renamed)));

        System.out.println("Email changed: "
                + !user.email().equals(renamed.email()));

        System.out.println("App roles: " + roles(user));

        System.out.println("Domain admin became app admin: "
                + roles(user).contains("ROLE_ADMIN"));

        System.out.println("Valid: "
                + authorize(TRUSTED_ISSUER, user, true));

        System.out.println("Disabled: "
                + authorize(TRUSTED_ISSUER, disabled, true));

        System.out.println("Stale: "
                + authorize(TRUSTED_ISSUER, user, false));

        System.out.println("Wrong issuer: "
                + authorize("https://untrusted.example", user, true));

        System.out.println("Missing app group: "
                + authorize(TRUSTED_ISSUER, noGrant, true));
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac DirectoryBehindIdpDemo.java
java DirectoryBehindIdpDemo
~~~

**Stdout chính xác:**

~~~text
Stable link: true
Email changed: true
App roles: [ROLE_REPORT_VIEWER]
Domain admin became app admin: false
Valid: ALLOW: ROLE_REPORT_VIEWER
Disabled: DENY: disabled directory account
Stale: DENY: stale directory state
Wrong issuer: DENY: untrusted issuer
Missing app group: DENY: missing application grant
~~~

**Diễn giải:** ID của cùng AD object không đổi khi rename trong mô hình; email không phải stable primary key; “Domain Admins” không được cấp quyền Spring admin; disabled, state stale, issuer khác hoặc thiếu group approved đều bị deny theo **policy mô phỏng**. Trong Spring thật, kiểm issuer không chỉ là so chuỗi: phải dùng framework OIDC/SAML/CAS validator xác minh signature/audience/expiry, state/nonce theo protocol. App có thể cần user status/revocation check riêng mới biết directory data còn fresh.

## 16. Account lifecycle và token/session cache

Một user có thể được AD disable ở thời điểm T nhưng vẫn còn:
- AD replication lag giữa DCs.
- IdP LDAP cache hoặc imported user record.
- IdP SSO session từ phiên trước.
- OIDC ID/Access Token chưa hết hạn.
- Spring Security local HTTP session.
- API permission cache.

~~~text
09:00 HR triggers offboarding
09:01 AD account disabled
09:03 IdP profile cache may be stale
09:05 Existing JWT may still be within exp
09:10 LDAP changed-users sync may run
09:15 Spring session may still be valid
~~~

Đây là thời điểm **giả định**. Hãy đặt và đo **deprovisioning SLA**, dùng các cơ chế phù hợp: short token TTL, revocation/introspection, session termination, event-driven provisioning hoặc policy checks khi truy cập tài nguyên nhạy cảm. Không mặc định LDAP directory outage làm mọi hiện hữu login fail, nhưng **không bao giờ fail-open** authentication mới khi credential/session chưa được xác minh.

## 17. Multi-domain AD, GC và directory failover

Global Catalog giúp tìm kiếm nhiều AD domains, nhưng thường chỉ chứa **partial attribute set**, không phải mọi directory attribute. IdP có thể cần query đúng domain DC để lấy thêm fields. Không tự đổi URL LDAP 636 sang GC 3269 rồi mặc định toàn bộ attribute/group mappers giống nhau.

Khi có forest trust, LDAP/GC lookup còn chịu DNS, firewall, AD ACLs, referrals và name suffix routing. Trust giữa Kerberos realms không tự cấp quyền đọc mọi directory entries. Một phương án thay thế cho nhiều tổ chức là đồng bộ **SCIM** hoặc federation OIDC/SAML qua identity broker, tránh mở rộng trực tiếp network access đến Domain Controllers ngoài doanh nghiệp.

## 18. Các kiểm thử bắt buộc theo tầng

| Trường hợp | Kỳ vọng |
| --- | --- |
| LDAPS CA/SAN hợp lệ | IdP kết nối thành công và verify server identity |
| CA không trust / cert sai hostname | TLS fail, không trust-all |
| Plain LDAP simple bind | Bị chặn theo policy; password không gửi cleartext |
| Service bind sai credential | Authn/search failure và cảnh báo |
| Search base DN sai | Không tìm user, báo lỗi directory phù hợp |
| Duplicate usernames | Không tự liên kết sai provider identities |
| Filter injection | Parameterization/escaping chặn search rộng |
| AD account disabled/expired | Login mới bị deny theo IdP policy |
| Rename/move AD user | Cùng objectGUID giữ identity link |
| Delete/recreate cùng email | Không tự thừa hưởng local account/role cũ |
| Import Users ON | Mapped profile được import, không import LDAP password |
| READ_ONLY mode | Không ghi directory fields ngoài chính sách |
| Changed-users sync | Group/department cập nhật trong SLA |
| Nested group | Chỉ role được app duyệt mới được map |
| Domain Admins group | Không tự tạo ROLE_ADMIN |
| GC query | Không giả định mọi attribute tồn tại trong GC |
| LDAP failover | Replicas cùng UUID, tránh independent directories |
| objectGUID decoder upgrade | Không duplicate/link sai user |
| OIDC issuer/signature/audience | Spring từ chối token không hợp lệ |
| SAML assertion signature/audience | Spring từ chối assertion sai |
| User disabled sau login | Hết quyền trong revocation SLA |
| PII minimization | Token không có fields/thừa group memberships |
| Directory down | IdP có fail policy; không tạo anonymous login thành authenticated |
| Cross-tenant access | Spring local authorization deny |
| Java demo | Compile/run đúng stdout nêu ở phần 15 |

Một unit test mock `OidcUser` chỉ giúp kiểm role/controller, **không chứng minh** LDAPS trust, user bind, group mapper, token issuance hoặc deprovisioning. Cần test cả IdP↔AD, IdP↔Spring, và business authorization.

### Các công cụ chẩn đoán

Trong lab được phép:

~~~bash
ldapsearch -x \
  -H ldaps://dc01.corp.example:636 \
  -D "CN=svc-ldap-reader,OU=Service Accounts,DC=corp,DC=example" \
  -W \
  -b "OU=Employees,DC=corp,DC=example" \
  "(&(objectCategory=person)(objectClass=user)(sAMAccountName=lnguyen))" \
  dn mail displayName
~~~

`-W` hỏi password tương tác; `-x` chỉ simple bind khi đã dùng **LDAPS có kiểm certificate**. Không dùng `-ZZ` cùng `ldaps://` vì một cái là STARTTLS và một cái là TLS ngay từ đầu; lựa chọn tùy endpoint và công cụ. Đây là request search, không xác minh một OIDC login. Không có stdout cố định vì host và DN minh họa.

## 19. Lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| LDAP error 49 | Invalid user hoặc service bind credential | Xác định account nào bị từ chối, không log secrets |
| LDAP error 32 | Base DN/OU sai | Kiểm directory namespace |
| LDAP error 50 | Insufficient access rights | Cấp read ACL tối thiểu, không Domain Admin |
| `PKIX path building failed` | CA chain/truststore sai | Sửa trusted CA/hostname |
| User không tìm thấy | Search filter/scope hoặc replication lag | Kiểm unique identity, base DN |
| User login IdP được, Spring không thấy email | Attribute mapper/scopes/sync | Kiểm IdP claim release, không tự query AD password |
| Mất roles sau đổi OU | Group mapping dựa vào DN cũ | Dùng identity/group contract bền vững |
| Duplicate identities | Email/username collision hoặc UUID format change | Kiểm provider+object ID và migration |
| Spring nhận 403 | Local RBAC/tenant không đủ | Kiểm ứng dụng, không mở LDAP bind rights |
| User disabled vẫn có session | Token/session TTL hoặc cache stale | Revocation/deprovision SLA |
| App nhận role admin ngoài ý muốn | Mapped AD groups quá rộng | App-specific allowlist và review |
| Recursive group search chậm | Group nesting và LDAP query scope | Điều chỉnh matcher, indexes, cache |
| GC thiếu field | Partial attribute set | Query đúng domain DC hoặc đổi data contract |
| IdP outage | Directory connection/credentials/MFA component | Phân loại network/TLS/bind/IdP protocol |

**Runbook theo thứ tự:** (1) directory entry/account state; (2) LDAP connector và bind/search; (3) IdP authentication/session/claims; (4) Spring protocol validation; (5) local business authorization. Không sửa lỗi Spring 403 bằng cách cấp Domain Admin cho IdP service bind.

## 20. Checklist triển khai và vận hành

- [ ] Phân biệt directory với IdP và Spring RP/SP.
- [ ] Có owner của schema, authoritative attributes và account lifecycle.
- [ ] Search không bị dùng thay authentication.
- [ ] Service bind credentials được bảo vệ và chỉ có quyền đọc tối thiểu.
- [ ] LDAPS/STARTTLS/SASL phù hợp, certificate chain/hostname verified.
- [ ] Không tắt LDAP signing/CBT policy chỉ để hỗ trợ client cũ.
- [ ] LDAP filters có escaping/parameterization, search scope giới hạn.
- [ ] Keycloak Import Users/Edit Mode/sync được kiểm đúng version.
- [ ] Password LDAP không bị copy vào IdP DB theo mô hình federation này.
- [ ] Dùng objectGUID/entryUUID có source namespace; không DN/email làm immutable key.
- [ ] OIDC user link theo verified `(iss, sub)`.
- [ ] Group mapper xử lý nested groups/role allowlist, không tự cấp admin.
- [ ] Account disabled, lockout, expiration có chính sách rõ.
- [ ] Token/session/cache/revocation SLA được giám sát.
- [ ] Claims per application được giới hạn PII và số lượng groups.
- [ ] GC partial attributes và multi-domain failover được test.
- [ ] Spring oauth2Login/saml2Login validate đúng issuer, audience, signature.
- [ ] App local roles, tenant và object authorization vẫn hoạt động độc lập.
- [ ] Có runbook và rollback cho LDAP provider, Keycloak upgrade và issuer migration.

## 21. Tài liệu chính thức

1. [RFC 4511 — LDAP v3](https://www.rfc-editor.org/rfc/rfc4511): bind/search và protocol.
2. [RFC 4513 — LDAP Authentication and Security](https://www.rfc-editor.org/rfc/rfc4513): credential validation và transport.
3. [RFC 4515 — LDAP Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515): escaping/filter injection.
4. [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): direct bind, LDAP provider và Active Directory.
5. [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Spring RP authentication flow.
6. [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html): Spring SP Assertion validation.
7. [Keycloak — Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/): LDAP/AD User Federation, sync và mappers.
8. [Keycloak — Upgrading Guide](https://www.keycloak.org/docs/latest/upgrading/): binary LDAP attribute decoder behavior.
9. [Microsoft — Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities): objectGUID và DN stability.
10. [Microsoft — UserAccountControl](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties): disabled flag.
11. [Microsoft — Search Filter Syntax](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax): nested group matching rules.
12. [Microsoft — LDAP Channel Binding](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding): TLS, signing, SASL và CBT.
13. [Microsoft — Configure LDAPS Certificates](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/configure-ldap-signing-certificates): AD DC cert và TLS.
14. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer/subject/ID Token validation.

**Tổng kết:** LDAP/AD làm **nguồn danh tính phía sau IdP**; IdP chứng thực session theo chính sách và phát token/assertion; Spring Security kiểm issuer/protocol rồi áp local RBAC/tenant. Có LDAP record không có nghĩa đã login, AD group không tự thành app admin, và disabled AD account không tự thu hồi tất cả tokens/sessions đang sống. Hãy ưu tiên stable IDs, TLS, least privilege, claim minimization và E2E revocation tests.