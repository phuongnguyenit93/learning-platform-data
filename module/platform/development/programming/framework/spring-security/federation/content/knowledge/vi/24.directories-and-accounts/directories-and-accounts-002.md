# Phân biệt truy vấn thư mục, xác thực trực tiếp và liên kết danh tính

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Thư mục và tài khoản. Bài Knowledge README này phân biệt ba thao tác thường bị gộp làm một: **directory lookup** (truy vấn dữ liệu người dùng/nhóm), **direct authentication** (xác minh credential trực tiếp với kho danh tính, ví dụ LDAP bind) và **identity linking** (liên kết định danh đã được xác thực ở một hệ thống bên ngoài với tài khoản cục bộ của ứng dụng). Bài tập trung vào Spring Security Servlet, Java 17+, LDAP/Active Directory, database, OIDC, SAML, Kerberos và những ranh giới tin cậy thiết yếu khi triển khai federation.

## 1. Ba câu hỏi khác nhau

Một hệ thống SSO có thể dùng cùng một Active Directory cho nhiều mục đích, nhưng ba nghiệp vụ sau **khác về đầu vào, đầu ra, bảo mật và người chịu trách nhiệm**.

1. **Truy vấn thư mục – Directory lookup:** “Trong directory có bản ghi nào khớp định danh này? Thuộc tính và các nhóm của nó là gì?”. Nó thường dùng search/read qua LDAP/AD hoặc directory API. **Tìm thấy một người dùng không có nghĩa người gọi đã chứng minh mình là người đó.**
2. **Xác thực trực tiếp – Direct authentication:** “Người đang đăng nhập có thật sự kiểm soát credential cần thiết không?”. Ví dụ Spring Security dùng LDAP **bind as user** để kiểm username/password hoặc local password encoder kiểm hash. Trả kết quả xác thực thành công/thất bại. **Xác thực thành công không tự chứng minh user có quyền ứng dụng nào.**
3. **Liên kết danh tính – Identity linking:** “Identity đã được nhà cung cấp A xác minh tương ứng với local account nào tại app B?”. Ví dụ OIDC `(issuer, subject)` được liên kết có kiểm soát với `localUserId`. Đây là **quy tắc ánh xạ identity được quản trị**, không phải phép tìm user theo email rồi tự ghép.

**Một câu để nhớ:** *Lookup tìm bản ghi; authentication chứng minh quyền kiểm soát credential; linking quyết định bản ghi bên ngoài tương ứng với tài khoản cục bộ nào.*

Một luồng thực tế có thể cần cả ba, nhưng **thứ tự, yêu cầu trust và thời điểm thực hiện phải rõ**.

## 2. So sánh trực diện

| Thuộc tính | Directory lookup | Direct authentication | Identity linking |
|---|---|---|---|
| Câu hỏi | Bản ghi nào? Thuộc tính nào? | Credential hợp lệ không? | External identity thuộc local account nào? |
| Đầu vào | Search base, filter, DN/ID | Username/password hoặc credential khác | External ID đã verify + proof account đang liên kết |
| Hệ thống điển hình | LDAP, AD, directory API, DB | LDAP bind, local password hash, KDC, IdP | Local identity-link DB/service |
| Kết quả | 0/1/n bản ghi, attributes, groups | Authenticated principal hoặc failure | Local user ID hoặc conflict/unlinked |
| Có chứng minh người gọi sở hữu identity? | **Không** | **Có khi verify đúng** | Chỉ nếu identity proof đã hợp lệ |
| Có đọc password user không? | Không nên; thường không thể | Có thể nhận password trong login form; không được log | Không cần password nếu đủ proof khác |
| Có sinh app role? | Có thể trả dữ liệu làm nguồn mapping | Không tự cấp business role | Không tự cấp role; chỉ nối identity→account |
| Failure tiêu biểu | Not found, multiple matches, timeout | Bad credentials, locked, disabled | Not linked, duplicate key, account conflict |
| Cần unique identity key? | Có để không nhầm bản ghi | Có để chọn principal/realm đúng | **Bắt buộc** cho uniqueness |
| Có thể diễn ra sau SSO không? | Có | Không cần xác thực lại bằng password nếu SSO đã verify | Có, sau một login được xác minh |
| Trust boundary | Tin dữ liệu directory theo quyền đọc | Tin verifier/credential protocol | Tin cả external proof và local account ownership |
| Nguy cơ nếu dùng sai | User enumeration, LDAP injection, sai nhóm | Credential leak, auth bypass | Account takeover, cross-tenant identity collision |

**Đừng gọi mọi lần truy vấn LDAP là “LDAP authentication”.** LDAP là một giao thức có operations search/read/bind/compare/modify; việc dùng LDAP **để đọc group** không giống thao tác **bind bằng mật khẩu user**.

## 3. Tình huống thực tế làm rõ sự khác biệt

Một công ty có:
- **Directory AD** quản lý nhân viên và AD group membership.
- **Spring Portal** với tài khoản `localUserId=1001`, tenant, quyền duyệt báo cáo.
- **OIDC Identity Provider** phục vụ login SSO.
- **Bảng external identities** nối định danh IdP với localUserId.

Khi Alice đăng nhập qua OIDC:
1. Spring Security chạy OIDC Authorization Code flow và xác minh ID Token/issuer/audience/nonce/state theo cấu hình.
2. Từ trusted OIDC principal, app nhận cặp `iss` và `sub`.
3. Identity-link table tra cặp đó ra localUserId=1001. **Đây là linking/resolution**, không phải kiểm password AD.
4. App có thể tra AD theo stable mapping để lấy group IDs. **Đây là lookup**, không phải xác thực lại.
5. App tra local DB roles, kiểm account active/tenant membership.
6. App tạo Spring Authentication/authorities theo policy và thực thi authorization từng resource.

Ngược lại, nếu app có **form username/password riêng dùng LDAP bind**, bước credential verification là **direct LDAP authentication**. Nó không tự tạo một OIDC identity link trừ khi có một workflow linking riêng được chủ động cho phép.

## 4. Directory là kho dữ liệu, không phải câu trả lời “đã đăng nhập?”

Một LDAP directory có thể lưu entries dạng DN:

~~~text
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
mail: alice@example.org
employeeNumber: E1042
~~~

DN/attributes là minh họa. Schema từng directory khác nhau; AD thường sử dụng `userPrincipalName`, `sAMAccountName`, `objectGUID`, `objectSid` và `memberOf`.

### 4.1. LDAP search

Một lookup đơn giản về mặt ý tưởng:

~~~text
base   = ou=people,dc=example,dc=org
scope  = subtree
filter = (&(objectClass=inetOrgPerson)(uid=alice))
attrs  = uid, cn, mail, entryUUID
~~~

Kết quả:
- **0 bản ghi:** không tìm được một identity trong scope; không có nghĩa password sai.
- **1 bản ghi:** có directory entry phù hợp; chưa xác thực người gọi.
- **Nhiều bản ghi:** search key/filter không unique hoặc directory sai; **không tự chọn bản ghi đầu** cho authentication/linking.

### 4.2. LDAP lookup có thể dùng service credentials

Ứng dụng dùng **read-only service bind** hoặc mTLS/SASL phù hợp để hỏi directory “alice có thuộc nhóm X không?”. Service account này chứng minh **quyền đọc directory của ứng dụng**; nó **không chứng minh một người đang dùng browser là Alice**.

**Anti-pattern nguy hiểm:**

~~~java
// KHÔNG AN TOÀN: tìm được bản ghi rồi tự coi browser là chủ tài khoản.
if (directory.findByUid(request.getParameter("uid")) != null) {
    // Không được tự tạo authenticated session ở đây.
}
~~~

Mọi client có thể gửi `uid=alice`. Lookup là nguồn dữ liệu, không phải credential proof.

### 4.3. Directory lookup phục vụ nhiều tác vụ không phải login

- Tìm user để hiển thị tên/email trong giao diện quản trị.
- Lấy group memberships sau Kerberos hoặc OIDC login.
- Kiểm account active/disabled trước khi cấp business access.
- Tìm manager/department của nhân viên.
- Đồng bộ thông tin public profile đã được duyệt.
- Định tuyến policy theo organization nhưng **không** thay authentication.
- Kiểm external identity link tới directory object.

Mỗi use case cần kiểm quyền đọc và privacy: search một số người không có nghĩa có thể hiển thị mọi attributes.

## 5. Direct authentication là xác minh credential

### 5.1. LDAP bind authentication

Spring nhận username/password trong một **login form có HTTPS**, xác định user DN rồi thử LDAP bind bằng chính credentials user. Directory server kiểm password và account policy; Spring nhận success/failure.

~~~text
Browser                 Spring Application                LDAP/AD
   |                            |                            |
   | POST /login                |                            |
   | username, password         |                            |
   +--------------------------->|                            |
   |                            | Search DN hoặc DN pattern |
   |                            +--------------------------->|
   |                            |<------ user DN ------------+
   |                            | Bind as user with password|
   |                            +--------------------------->|
   |                            |<------ success/failure ----+
   |                            | Nếu success, load group/role
   |                            | và tạo Authentication
   |<----------- result --------+                            |
~~~

**Điểm quan trọng:** Trong bind authentication, ứng dụng không cần đọc password hoặc hash password từ LDAP rồi tự so sánh. LDAP server kiểm credentials; Spring Security LDAP dùng `LdapAuthenticator` thay vì mặc định `UserDetailsService` của form authentication dựa DB. <escape><</escape>Điều này không có nghĩa login form không nhận password: Spring **có thể nhận password ở inbound request** để chuyển bind, do đó phải bảo vệ TLS, request logging và secret handling.</escape>

### 5.2. Password comparison là cơ chế khác bind

Spring LDAP cũng hỗ trợ **password comparison**:
- Ứng dụng dùng LDAP compare operation hoặc lấy attribute password/hash khi directory policy cho phép.
- So sánh credential được cung cấp với giá trị lưu theo một algorithm/PasswordEncoder thích hợp.
- LDAP compare có những giới hạn đối với salted hash như tài liệu Spring nêu.
- Không dùng `NoOpPasswordEncoder` cho production và không tự đổi dạng password hashing của directory nếu không có hợp đồng xác thực.

Đừng gộp “LDAP bind”, “LDAP compare” và “chạy SELECT user WHERE username=...” thành một thao tác.

### 5.3. Local database password authentication

Một ứng dụng dùng password hashes trong DB có thể:
1. Load `UserDetails` bằng `UserDetailsService`.
2. Dùng `DaoAuthenticationProvider` và `PasswordEncoder` (ví dụ bcrypt/Argon2 theo policy) để verify password.
3. Trả Authentication cùng mapped GrantedAuthorities.

**Khác LDAP bind:** ứng dụng sở hữu password hash/encoder logic; với LDAP bind, directory là nơi xác minh credential. Cả hai là **direct authentication** nhưng trust boundaries và vòng đời secrets khác nhau.

### 5.4. Direct authentication không đồng nghĩa group lookup

Có thể:
- Bind thành công nhưng user không có role app → authenticated nhưng bị 403.
- Lookup user/AD groups thành công nhưng bind password fail → không tạo authenticated session.
- AD account disabled dù có entry → phải từ chối theo auth/account lifecycle policy.
- User đã login qua IdP OIDC → app lookup AD groups mà không bind password lần nữa.

Phân biệt này giúp chẩn đoán chính xác “không tìm được user”, “password sai” và “không đủ quyền”.

## 6. Spring Security LDAP: cấu hình bind chuẩn

Tài liệu Spring Security cho Servlet dùng `LdapBindAuthenticationManagerFactory` với `BaseLdapPathContextSource`.

Tệp `src/main/java/com/example/security/LdapBindConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
public class LdapBindConfiguration {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");

        return factory.createAuthenticationManager();
    }
}
~~~

Giải thích:
- `contextSource` chứa LDAP connection/base DN và cấu hình TLS/trust.
- `setUserSearchBase` giới hạn scope, tránh tìm cả directory vô cớ.
- `setUserSearchFilter` là pattern được Spring xử lý với login username; không nối chuỗi bất kỳ từ HTTP input.
- `createAuthenticationManager()` trả manager dùng cho **username/password LDAP login**, không phải một directory lookup service đơn thuần.
- User DN pattern cũng có thể dùng nếu directory có layout cố định, ví dụ `uid={0},ou=people`.
- Ví dụ là **Spring configuration class**, không chạy bằng `javac` trần; cần context source, Spring dependencies, login filter/HTTP Security, LDAP server và TLS thật.
- Đối với Active Directory, có provider chuyên biệt `ActiveDirectoryLdapAuthenticationProvider` theo UPN convention; hãy dùng phiên bản và cấu hình đúng domain/URL/account status, không mặc định bind LDAP general sẽ xử lý mọi AD feature như provider AD.

**Không tạo login session bằng cách gọi directory.search() rồi return success.** Manager phải chứng minh password hoặc credential đúng.

### 6.1. Cấu hình quyền qua LDAP authorities populator

Spring Security có `LdapAuthoritiesPopulator` để load authorities sau LDAP authentication. Ví dụ fragment:

~~~java
@Bean
LdapAuthoritiesPopulator ldapAuthorities(
        BaseLdapPathContextSource contextSource) {

    DefaultLdapAuthoritiesPopulator populator =
            new DefaultLdapAuthoritiesPopulator(
                    contextSource, "ou=groups");

    populator.setGroupSearchFilter("(member={0})");
    return populator;
}
~~~

Cần các imports:
- `org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator` (kiểm API thực của version).
- `org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator` theo package thực của Spring Security LDAP release.

Trong source theo Spring Security version, class `DefaultLdapAuthoritiesPopulator` thường nằm dưới `org.springframework.security.ldap.userdetails`. Đoạn này là **bean fragment**, không phải module build độc lập; phải gắn bằng `factory.setLdapAuthoritiesPopulator(populator)` và kiểm group mapping policy.

**Vận hành:** Group search trả directory groups, **không** mặc nhiên biến mọi LDAP group thành `ROLE_ADMIN`. Chỉ cấp authorities theo allowlist business policy.

## 7. Spring LDAP: truy vấn directory mà không authenticate user

Một fragment dùng `LdapTemplate` và `LdapQueryBuilder` khác hoàn toàn bind authentication:

~~~java
package com.example.directory;

import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryReader {

    private final LdapTemplate ldap;

    public DirectoryReader(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<String> lookupUids(String uid) {
        LdapQuery q = query()
                .base("ou=people")
                .where("uid").is(uid)
                .and("objectClass").is("inetOrgPerson");

        return ldap.search(q, (AttributesMapper<String>)
                attrs -> (String) attrs.get("uid").get());
    }
}
~~~

**Đây là Java class có phụ thuộc Spring LDAP**, không phải standalone program. Nó chỉ thực hiện search với account đã cấp phép cho LdapTemplate. Sau khi nhận danh sách phải xử lý 0/1/n entries theo policy; nếu dùng để identity resolution, yêu cầu đúng **một** kết quả.

**Tại sao builder quan trọng?** Spring LDAP `LdapQueryBuilder` escape những ký tự nguy hiểm trong filter values, tránh LDAP injection. Không viết:

~~~java
// KHÔNG AN TOÀN: filter injection.
String filter = "(uid=" + request.getParameter("uid") + ")";
~~~

Đầu vào đáng tin của directory/API cũng cần escape cho LDAP filter hoặc parameterize SQL; “đã xác thực Kerberos” không khiến chuỗi principal an toàn để nối vào câu truy vấn.

### 7.1. Lookup không chứa password

`lookupUids("alice")` không nhận user password, không kiểm ai đang sử dụng browser và không tạo Spring Authentication. Nó phù hợp để lookup profile/groups **sau khi một authentication flow khác đã thành công**.

### 7.2. LDAP search nên trả stable identifier

Nếu mục đích là tạo identity linking, cần đọc một immutable/stable directory ID:
- LDAP generic có thể có `entryUUID` nếu server/schema hỗ trợ.
- Active Directory thường dùng `objectGUID` cho user object và `objectSid` cho security identity.
- `uid`, `cn`, `mail` hoặc `displayName` có thể được đổi, trùng hoặc tái cấp.

Ví dụ code chỉ trả UID để minh họa lookup, **không đề xuất dùng UID làm global immutable external key trong mọi directory**.

## 8. Active Directory: AD auth và AD lookup khác nhau

AD cung cấp những khái niệm:
- `userPrincipalName` (UPN) và `sAMAccountName` (login-name conventions).
- `objectGUID` (directory object identity).
- `objectSid` (security identifier).
- `memberOf`/nested group membership.
- Account disabled/locked/expired policies.
- SPNs và Kerberos tickets trên AD domain controllers.
- Directory query qua LDAP/LDAPS.

### 8.1. AD password login

Spring `ActiveDirectoryLdapAuthenticationProvider` là provider chuyên biệt:
- Thường xác thực với UPN theo `username@domain`.
- Có thể dùng search filter riêng.
- Xử lý AD-specific error/sub-codes theo cấu hình.
- Sau auth có thể lấy group memberships/authorities.

Đây vẫn là **direct authentication** khi ứng dụng nhận username/password. Nếu browser SSO qua Kerberos thì application nhận SPNEGO ticket, **không cần bắt user điền lại AD password để tra groups**.

### 8.2. AD query sau Kerberos/OIDC

Ứng dụng có thể dùng read-only service credential để tra `objectGUID` và approved groups cho một verified principal. Khi làm vậy, không gọi lookup đó là “AD login”. Kerberos/OIDC provider đã thực hiện authentication ở chỗ khác; directory chỉ là nguồn attributes/entitlements.

### 8.3. Nhận diện một user qua AD

Có thể cần mapping:
- Verified Kerberos `user@REALM` → AD user object.
- Verified OIDC `iss+sub` → approved link → localUserId → AD objectGUID.
- Local account → AD objectGUID để lấy groups.
- Nested AD groups → application-role allowlist.

Không suy ra một OIDC user thuộc một AD record chỉ vì hai bên có cùng email.

## 9. Federation authentication khác direct LDAP bind

Spring Security federation thường có:
- **OIDC/OAuth2 Login:** Browser redirect IdP, Spring nhận Authorization Code, thực hiện token exchange và xác minh ID Token theo cấu hình, rồi nhận `OidcUser`/claims.
- **SAML 2.0 Login:** Spring SP verify Response/Assertion signatures, issuer, conditions, audience/recipient, response correlation theo profile và nhận `Saml2AuthenticatedPrincipal`/attributes.
- **Kerberos/SPNEGO:** GSS acceptor dùng service keytab xác minh AP-REQ, nhận verified Kerberos client principal.
- **CAS native protocol:** Client nhận Service Ticket và kiểm qua CAS Server validation endpoint.

**Không cái nào mặc nhiên là LDAP password bind trong ứng dụng web.** Federation service có thể dựa vào directory ở IdP, hoặc application lookup directory sau login, nhưng verifier hiện tại là giao thức IdP/KDC/CAS tương ứng.

### 9.1. Bảng phân loại tình huống

| Tình huống | Authentication mechanism | Lookup | Linking |
|---|---|---|---|
| Login form username/password, LDAP bind | Direct LDAP bind | Tìm DN/groups có thể kèm | Không bắt buộc |
| Login form local DB password | DaoAuthenticationProvider/PasswordEncoder | UserDetailsService DB | Không bắt buộc |
| Browser Kerberos SPNEGO | Kerberos GSS ticket verification | AD/LDAP groups sau ticket | Có thể, nếu local account |
| Spring OIDC Login | ID Token/code flow IdP đã verify | UserInfo, local DB hoặc AD | Thường cần local mapping |
| Spring SAML Login | Signed Response/Assertion protocol verification | SAML attributes, local DB/AD | Thường cần local mapping |
| CAS Ticket login | CAS ticket validation | Local directory/DB | Có thể |
| Admin tìm nhân viên theo mail | **Không có end-user auth từ lookup** | Directory search | Không tự tạo link |
| User đang login bấm “Liên kết tài khoản” | Phải có current session và external proof | Lookup có thể hỗ trợ | Explicit identity linking |
| SCIM user provisioning | Không phải end-user login | Tạo/cập nhật directory records | Có thể chuẩn bị identity links, phải approved |

**Đừng tạo một authentication provider từ API search/read:** tìm được directory entry chưa chứng minh credential.

## 10. Identity linking: nối external identity với local account

Một ứng dụng có local accounts:
~~~text
local_users
  id         uuid
  status     ACTIVE / DISABLED
  tenant_id  tenant-a
  created_at timestamp
~~~

External identities có thể được gắn như:
~~~text
external_identity_links
  provider_type  OIDC | SAML | KERBEROS | LDAP | CAS
  issuer_or_realm
  external_subject
  local_user_id
  tenant_scope
  link_state     ACTIVE | REVOKED
  linked_at
  linked_by
~~~

Đây là **schema concept**, không phải schema mặc định của Spring. Một local account có thể có nhiều external identities đã được phê duyệt, và một external identity chỉ nên trỏ tới **một** local account trong một scope đã định nghĩa.

### 10.1. Identity linking là quyết định tin cậy lâu dài

Khi link được tạo, các lần login sau bằng cùng external identity thường tìm được local user ngay. Link sai có thể trao quyền truy cập tài khoản người khác dù IdP authentication hoàn toàn hợp lệ.

**Vì vậy linking là một security-sensitive operation**, không phải thao tác “INSERT nếu email giống nhau”. Cần authn proof, explicit intent, session freshness, CSRF protection, uniqueness và audit.

### 10.2. External key của OIDC

OpenID Connect Core quy định cặp **`iss` + `sub`** là khóa định danh ổn định trong scope của IdP:
- `iss` = issuer đã xác minh (URL/issuer identifier).
- `sub` = subject identifier trong issuer.
- Không dùng `email`, `preferred_username`, `name` làm unique key tin cậy giữa users/issuers.

Ví dụ:
~~~text
OIDC
issuer  = https://login.example.org/realms/employees
subject = 248d2bf1-...
localUserId = 1001
~~~

OIDC email có thể được đổi, tái sử dụng hoặc không được cung cấp; `email_verified` chỉ nói về assertion của provider theo policy, **không đủ để tự link sang local account nhạy cảm**. Cũng phải validate ID Token và khi dùng UserInfo, xác nhận `UserInfo.sub` khớp ID Token `sub`.

### 10.3. External key của SAML

SAML không có một cặp cố định giống OIDC iss+sub trong mọi deployment. Identity key cần dựa vào:
- Trusted IdP entityID/issuer.
- NameID và `Format`/`NameQualifier`/`SPNameQualifier` nếu profile phù hợp.
- Hoặc một attribute ổn định do hợp đồng IdP–SP xác định, có uniqueness, reassign và lifecycle policy rõ.

**Không coi NameID luôn ổn định:** transient NameID có thể thay mỗi lần login; email-format NameID không mặc nhiên immutable. Khi thay IdP/certificate/name mapping, cần link migration chính thức và kiểm chống account takeover.

### 10.4. External key của Kerberos/AD

Với Kerberos, dùng verified **full principal + realm** theo trust contract. Nếu AD đổi UPN, có thể dùng approved mapping tới `objectGUID/objectSid` để duy trì local identity. Không cắt `@REALM` hoặc tự lower-case all names rồi gộp account khác realm.

### 10.5. External key của LDAP direct auth

Nếu direct LDAP bind đã xác thực user, có thể map kết quả tới stable directory ID:
- Directory entryUUID theo schema server.
- AD objectGUID/objectSid.
- DN/uid có thể thay khi rename/move, nên cần migration policy.

Không biến việc tìm được một entry LDAP theo email thành proof rằng browser sở hữu account đó.

### 10.6. Identity key phải có namespace/provider

Một external subject string như `alice` không unique trên toàn hệ thống. Khóa identity nên chứa:
- Mechanism/provider type.
- Trusted issuer/realm/directory instance.
- Subject ID chính xác.
- Nếu multi-tenant: scope thực sự cần thiết theo hợp đồng provider/local identity model.

**Không thay đổi issuer string theo redirect URL không được xác minh**; issuer lấy từ trusted provider/metadata sau protocol validation. Không tự merge subject của hai issuers khác nhau.

## 11. Liên kết tài khoản an toàn yêu cầu chứng minh hai phía

Giả sử Alice đã login local account và muốn liên kết SSO của công ty:

1. Alice có **local session đã authenticated**, còn hiệu lực và đủ freshness.
2. Alice chủ động chọn “Liên kết tài khoản doanh nghiệp” qua POST được CSRF-protected.
3. App tạo link intent một lần, có nonce/state/TTL gắn session/localUserId và expected provider.
4. Browser khởi chạy OIDC/SAML/other trusted authentication flow.
5. Spring xác minh protocol response, bảo đảm external identity thực sự được authenticate và thuộc expected provider/tenant.
6. App chuẩn hóa external key theo protocol contract.
7. App kiểm external key chưa linked tới localUser khác, và local account còn active.
8. Transaction/unique constraint tạo link atomically; concurrent attempts không thể chiếm account.
9. Audit user, provider, link key hash, timestamp, authentication context, outcome.
10. Redirect tới trang thông báo thành công, xóa pending intent; **không** phát lệnh chuyển tiền hoặc side effect khác chỉ vì auth callback thành công.

**Nếu user chưa có local session**, quy trình account recovery/link phải có proof tương đương về ownership local account. Tìm một local user có email trùng với IdP không đủ.

### 11.1. Cần xác minh control local account

Có nhiều cách tùy risk:
- Reauthenticate bằng credential local theo security policy.
- Xác nhận MFA đang gắn với local account.
- Với tài khoản doanh nghiệp do IAM quản trị, dùng approval workflow/gateway đã xác thực hai phía.
- Một account recovery flow có rate-limit, anti-enumeration, proof of possession và audit.

Không dùng “email từ IdP bằng email local” làm proof duy nhất cho tài khoản có quyền cao.

### 11.2. Trường hợp external identity đã linked

Nếu link external key đã tồn tại:
- **Cùng localUserId:** có thể coi là idempotent (đã liên kết), không tạo duplicate.
- **Khác localUserId:** **conflict** và từ chối, không silently reassign.
- **Link đã revoked:** policy có thể yêu cầu manual re-approval, không tự revive khi login.
- **Local account disabled:** không cho link mới hoặc login theo chính sách.
- **Tenant khác:** không bypass tenant isolation, không merge mặc định.

### 11.3. Unlink cũng là nghiệp vụ bảo mật

Cần bảo vệ:
- User đã reauth/step-up gần đây.
- Không unlink phương thức login cuối cùng nếu khiến account không thể khôi phục, trừ khi có recovery policy rõ.
- Không cho unlink của localUser khác.
- Audit và invalidate sessions/tokens khi cần.
- Không tự chuyển quyền localUser khi một provider thay `sub` hoặc NameID.

## 12. JIT provisioning khác auto-link tài khoản cũ

**Just-In-Time provisioning** nghĩa là tạo local account khi gặp external identity hợp lệ lần đầu, theo chính sách onboarding. Nó không đồng nghĩa nối external identity vào một account hiện có vì email trùng.

### 12.1. Kịch bản chưa có external link

Sau OIDC/SAML login thành công, link lookup không tìm thấy:
1. Nếu provider/tenant không có trong allowlist → deny.
2. Nếu không có entitlement onboarding → deny/request approval.
3. Nếu chính sách cho phép JIT → tạo **local account mới** và external link atomically, với quyền tối thiểu.
4. Nếu có local account email trùng → không tự ghép; yêu cầu explicit linking/approved enterprise account resolution.
5. Nếu directory có user cùng username nhưng là person khác → không merge.
6. Nếu có race condition → database uniqueness xử lý, transaction retry/handoff an toàn.

### 12.2. Quyền mặc định phải tối thiểu

JIT tạo account không nên mặc định cấp:
- `ROLE_ADMIN`.
- Quyền duyệt chi tiền.
- Quyền truy cập mọi tenant.
- Quyền từ nhóm được user tự khai.
- Truy cập tài nguyên đã thuộc local account khác.

Nguồn quyền cần là approved group/entitlement mapping có tenant scope và revocation lifecycle.

## 13. Khóa unique, giao dịch và tránh account takeover

Một schema SQL tham khảo (dialect có thể khác theo DB):

~~~sql
CREATE TABLE local_user (
    id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    tenant_id VARCHAR(64) NOT NULL
);

CREATE TABLE external_identity_link (
    provider_type VARCHAR(24) NOT NULL,
    trusted_issuer VARCHAR(512) NOT NULL,
    subject_key VARCHAR(512) NOT NULL,
    local_user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    linked_at TIMESTAMP NOT NULL,
    PRIMARY KEY (provider_type, trusted_issuer, subject_key),
    FOREIGN KEY (local_user_id) REFERENCES local_user(id)
);
~~~

**Ý nghĩa:**
- Unique composite key bảo đảm cùng một external identity không gắn tới hai local users.
- Foreign key bảo đảm target account tồn tại.
- Tạo link trong transaction, không dùng “SELECT chưa thấy, rồi INSERT” mà thiếu database unique guarantee.
- Mô hình subject/issuer lengths/index phải theo DB và provider contract; có thể dùng keyed digest có collision policy nếu các trường quá dài.
- Nếu kiến trúc tenant-specific identity key, cần định nghĩa rõ tenant nằm ở PK hay thuộc local user; **đừng thêm tenant theo browser request để cho phép cùng identity chiếm nhiều accounts ngoài policy**.
- Có quy định re-link/unlink/audit state, không chỉ một row bất biến.
- Credential secrets, passwords, tokens, SAML assertions không nên nằm trong linking table.

**Concurrency scenario:** Hai phiên cùng cố link một external key vào hai local accounts. Chỉ một transaction được commit; phiên còn lại nhận conflict và không được overwrite. Đây là cơ chế quan trọng để chống takeover trong môi trường nhiều pods.

## 14. Java 17 độc lập: mô phỏng ba hoạt động riêng

Đoạn code sau **chạy bằng JDK 17+**, không cần LDAP, Spring hay IdP. Nó tách việc directory lookup, credential verification đã có từ trusted provider và identity linking. Các kết quả là **mô phỏng**, không được dùng như cơ chế authentication production.

Tệp `DirectoryAuthLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class DirectoryAuthLinkDemo {

    record ExternalKey(String provider, String issuer, String subject) {
        ExternalKey {
            Objects.requireNonNull(provider);
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(subject);
            if (provider.isBlank() || issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("Empty identity key");
            }
        }
    }

    record LocalAccount(String id, boolean enabled) {
    }

    enum LinkOutcome {
        LINKED, ALREADY_LINKED, CONFLICT, REJECTED
    }

    private static final Map<String, String> DIRECTORY = Map.of(
            "alice", "alice@example.org");

    private static final Map<String, LocalAccount> ACCOUNTS = Map.of(
            "U1001", new LocalAccount("U1001", true),
            "U2002", new LocalAccount("U2002", true),
            "U3003", new LocalAccount("U3003", false));

    private static final Map<ExternalKey, String> LINKS = new HashMap<>();

    static boolean directoryContains(String uid) {
        return DIRECTORY.containsKey(uid);
    }

    static LinkOutcome link(
            ExternalKey key,
            String localId,
            boolean localSessionVerified,
            boolean externalCredentialVerified) {

        LocalAccount account = ACCOUNTS.get(localId);
        if (!localSessionVerified
                || !externalCredentialVerified
                || account == null
                || !account.enabled()) {
            return LinkOutcome.REJECTED;
        }

        String existing = LINKS.get(key);
        if (existing != null) {
            return existing.equals(localId)
                    ? LinkOutcome.ALREADY_LINKED
                    : LinkOutcome.CONFLICT;
        }

        LINKS.put(key, localId);
        return LinkOutcome.LINKED;
    }

    public static void main(String[] args) {
        ExternalKey alice = new ExternalKey(
                "OIDC", "https://idp.example.org", "sub-123");
        ExternalKey other = new ExternalKey(
                "OIDC", "https://other-idp.example.org", "sub-123");

        System.out.println("directory-found=" +
                directoryContains("alice"));
        System.out.println("lookup-authenticates=false");
        System.out.println("unverified=" +
                link(alice, "U1001", true, false));
        System.out.println("link=" +
                link(alice, "U1001", true, true));
        System.out.println("repeat=" +
                link(alice, "U1001", true, true));
        System.out.println("conflict=" +
                link(alice, "U2002", true, true));
        System.out.println("other-issuer=" +
                link(other, "U2002", true, true));
        System.out.println("disabled=" +
                link(new ExternalKey(
                     "OIDC", "https://idp.example.org", "sub-999"),
                     "U3003", true, true));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DirectoryAuthLinkDemo.java
java DirectoryAuthLinkDemo
~~~

**Stdout chính xác:**

~~~text
directory-found=true
lookup-authenticates=false
unverified=REJECTED
link=LINKED
repeat=ALREADY_LINKED
conflict=CONFLICT
other-issuer=LINKED
disabled=REJECTED
~~~

**Diễn giải:**
1. Directory tìm thấy Alice nhưng kết quả lookup **không phải login**.
2. External proof chưa được verify thì không cho link dù local session hợp lệ.
3. Link đã tạo cùng account là idempotent.
4. External key đã gắn U1001 không thể bị U2002 âm thầm chiếm.
5. Cùng subject text nhưng **khác issuer** là identity khác.
6. Local account disabled không được dùng làm đích link.

**Giới hạn bảo mật:** Hai boolean `localSessionVerified` và `externalCredentialVerified` chỉ là mô phỏng. Ở production, **không cho HTTP client truyền hai boolean rồi tin**; phải dựa trên trusted session server-side, fully validated OIDC/SAML/Kerberos result, CSRF/state/nonce/freshness và transactional repository. `HashMap` chỉ dùng cho demo single-thread; hệ nhiều nodes phải dùng database unique constraint/transaction.

## 15. Java 17 độc lập: minh họa quyết định thao tác nào là authentication

Ví dụ này không đòi password thật; nó phân loại mục đích API, cho thấy chỉ tìm thấy directory entry không tạo authenticated principal.

Tệp `IdentityOperationDemo.java`:

~~~java
public class IdentityOperationDemo {

    enum Operation {
        DIRECTORY_LOOKUP,
        PASSWORD_AUTHENTICATION,
        FEDERATION_AUTHENTICATION,
        IDENTITY_LINKING
    }

    static String result(Operation op) {
        return switch (op) {
            case DIRECTORY_LOOKUP -> "ATTRIBUTES_NOT_IDENTITY_PROOF";
            case PASSWORD_AUTHENTICATION ->
                    "CREDENTIAL_VERIFICATION_REQUIRED";
            case FEDERATION_AUTHENTICATION ->
                    "PROTOCOL_PROOF_VERIFICATION_REQUIRED";
            case IDENTITY_LINKING ->
                    "TWO_SIDED_PROOF_AND_UNIQUE_BINDING";
        };
    }

    public static void main(String[] args) {
        for (Operation op : Operation.values()) {
            System.out.println(op + "=" + result(op));
        }
    }
}
~~~

Chạy:

~~~bash
javac IdentityOperationDemo.java
java IdentityOperationDemo
~~~

**Stdout chính xác:**

~~~text
DIRECTORY_LOOKUP=ATTRIBUTES_NOT_IDENTITY_PROOF
PASSWORD_AUTHENTICATION=CREDENTIAL_VERIFICATION_REQUIRED
FEDERATION_AUTHENTICATION=PROTOCOL_PROOF_VERIFICATION_REQUIRED
IDENTITY_LINKING=TWO_SIDED_PROOF_AND_UNIQUE_BINDING
~~~

Mô hình chỉ dùng để xác định responsibility của một lớp Java. Nó không thể thay LDAP bind authentication hoặc token signature verification.

## 16. Spring Security OIDC: authority mapping không đồng nghĩa account linking

Spring `oauth2Login()` có thể cấu hình OIDC `OidcUserService` hoặc `GrantedAuthoritiesMapper`:
- IdP cung cấp verified claims/identity sau protocol authentication.
- UserInfo có thể bổ sung attributes sau khi Spring kiểm source và subject.
- `OidcUser.getAuthorities()` có thể bao gồm authorities theo OAuth scopes và `OidcUserAuthority`.
- App có thể map sang `GrantedAuthority` business roles.
- Một **identity-link service riêng** tìm localUserId từ `iss+sub`.

Cảnh báo:
- `SCOPE_profile` hay `OIDC_USER` không tự là `ROLE_ADMIN`.
- `email_verified=true` không tự cho phép link với account local mang email giống.
- `UserInfo.sub` cần khớp `ID Token.sub`; OpenID Connect Core quy định rõ.
- Không lấy issuer từ một URL browser tùy ý, mà từ provider metadata được cấu hình và response validation.
- Nếu identity unlinked, có thể từ chối hoặc bắt onboarding/JIT theo policy; không tự cấp quyền cao.

### 16.1. Fragment cấu hình Spring OIDC

~~~java
@Bean
SecurityFilterChain oidcSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(approvedOidcUserService())));
    return http.build();
}
~~~

Đây là **method fragment**: `approvedOidcUserService()` cần thực hiện protocol-validated OidcUser delegation, identity linking và authority policy, đồng thời trả type `OAuth2UserService<OidcUserRequest, OidcUser>` phù hợp với framework version. Mã không chạy độc lập; không nhận xét là một full secure OIDC integration chỉ từ fragment này.

**Quan trọng:** Không thay Spring OIDC protocol verifier bằng một hàm lookup user theo email. Identity link chỉ được chạy sau trusted token validation.

## 17. Spring SAML và Kerberos: nối principal khác nhau

### 17.1. SAML

Sau `saml2Login()` và SAML Response verification, Spring có authenticated principal và attributes. Identity linking cần biết:
- Trusted IdP issuer.
- Stable subject contract (NameID Format/qualifiers hoặc attribute định danh ổn định).
- Điều kiện signature, audience, recipient, replay, response correlation.
- Tenant/IdP registration/metadata trust.

SAML email attribute không đủ để tự link; NameID transient không ổn định cho account lâu dài. Quy tắc identity key phải được thỏa thuận với IdP.

### 17.2. Kerberos

Sau `SpnegoAuthenticationProcessingFilter` và `KerberosServiceAuthenticationProvider` verify ticket:
- Verified full principal có realm.
- App có thể dùng directory lookup để lấy AD group/user object.
- App có thể link principal/objectGUID tới localUserId.
- Không cần nhận password user hoặc LDAP bind lại nếu chỉ muốn lookup groups.

**Không bỏ realm:** `alice@REALM-A` khác `alice@REALM-B`. Nếu short names trùng, phải giải quyết theo stable directory linking và realm trust policy.

### 17.3. CAS native

CAS Service Ticket validation xác minh một CAS principal sau back-channel; có thể map sang localUserId bằng trusted CAS issuer/service configuration và stable principal contract. CAS ticket **không phải Kerberos ticket**, và việc một CAS server dùng LDAP backend không có nghĩa client đang chạy LDAP bind.

## 18. Quyền ứng dụng phải được tải riêng

Sau direct authentication hoặc federation authentication:
1. Có identity đã được chứng minh.
2. Identity resolver/link service cho localUserId.
3. Directory/DB/IAM lookup lấy account status/roles/memberships.
4. Chỉ allowlisted groups/entitlements mới tạo `GrantedAuthority`.
5. Resource/tenant authorization quyết định action.

Ví dụ:
- AD group “GG-Report-Readers” có thể map `ROLE_REPORT_VIEW`.
- Group “Domain Admins” **không tự là** ROLE_ADMIN của portal.
- `hasAuthority("ROLE_REPORT_VIEW")` so chuỗi chính xác.
- `hasRole("REPORT_VIEW")` dùng role prefix mặc định, thường kiểm `ROLE_REPORT_VIEW`.
- Nếu app phân quyền per tenant, role toàn cục chưa đủ.

### 18.1. Identity lifecycle khác role lifecycle

Account có thể còn identity link hợp lệ trong khi:
- Local account bị disable.
- Group/role bị thu hồi.
- Tenant membership mất hiệu lực.
- Directory đã offboard user.
- Spring HttpSession vẫn đang giữ authorities snapshot cũ.

**Link không đồng nghĩa authorization trọn đời.** Cần TTL/cache invalidation, account state recheck và session revocation policy.

### 18.2. Không tạo ROLE_ADMIN từ external claims một cách máy móc

Token claim như `groups=["Admin"]` hoặc `email_domain=example.org` chỉ là **dữ liệu từ IdP**, cần tin đúng issuer/audience và mapping policy theo stable IDs, scope tenant; không cộng tất cả claim thành application authorities. Authorization phải thực thi least privilege.

## 19. Account linking và multi-tenant

Một doanh nghiệp có nhiều tenant/organizations, mỗi tenant có thể có:
- AD domain khác.
- OIDC issuer khác.
- SAML IdP khác.
- User có cùng email/username nhưng khác real identity.
- Local roles/permissions khác nhau.

Một identity từ tenant A **không tự được link sang local account tenant B**. Cần:
- Trusted issuer/realm/provider registration.
- Approved localUserId và tenant membership.
- Unique identity key và uniqueness policy.
- Cross-tenant linking approval/recovery khi thật sự cần.
- Explicit conflict handling và audit.

**Cẩn thận uniqueness theo tenant:** Nếu key duy nhất chỉ là `(tenant, issuer, sub)`, cùng identity có thể được linked tới hai accounts ở hai tenants; điều này có thể hợp lệ hoặc trái security model. Chọn global/provider scoped uniqueness dựa vào hợp đồng, không do user tự khai tenant trong query.

## 20. Cache, offboarding và account status

Một môi trường production có các caches:
- LDAP/AD user attributes/group memberships.
- Local identity-link resolution.
- OIDC/SAML/Kerberos authenticated principal/session.
- Spring SecurityContext/HttpSession có authorities snapshot.
- Authorization decisions theo resource.

Các caches có **lifecycle khác nhau**. Khi admin disable user hoặc remove group:
- Directory search có thể trả status mới.
- Identity link vẫn tồn tại.
- Spring HttpSession có thể vẫn authenticated.
- Group cache có thể chưa hết TTL.
- Ticket/token IdP có thể vẫn chưa hết hạn.

Giải pháp:
1. Xác định revocation SLA cho từng loại role.
2. Khi account disabled, từ chối login và invalidate/revoke sessions theo risk.
3. Khi role thay đổi, refresh authorities/invalidate cache.
4. Sensitive action kiểm entitlement gần thời điểm sử dụng.
5. Logs/audit thể hiện provider, localUserId, policy version và outcome nhưng không raw tokens.
6. Khi directory/IAM unavailable, **fail closed** cho new authentication/role elevation; stale-cache policy chỉ áp dụng nếu đã được phê duyệt rõ.
7. Không nghĩ một lần LDAP search mới sẽ tự cập nhật SecurityContext của mọi browser session.

## 21. Quy tắc bảo mật LDAP và credential handling

### 21.1. LDAP injection

Dữ liệu được gửi tới search filter phải escape theo RFC 4515 hoặc dùng Spring `LdapQueryBuilder`:
- Dấu `*`, `(`, `)`, backslash, NUL có ý nghĩa đặc biệt trong LDAP filter.
- DN escaping khác filter escaping.
- Không nối `"(uid=" + input + ")"`.
- Giới hạn base DN/search scope/size/time.
- Không cho directory search trả toàn bộ users/attributes khi không cần.

### 21.2. Bind password và LDAP TLS

Nếu dùng direct LDAP bind:
- Form login/browser→app phải qua HTTPS.
- App→LDAP nên dùng LDAPS hoặc StartTLS/secured SASL theo policy.
- Xác minh CA chain/hostname; không bỏ TLS validation.
- Không log password, bind DN/password, request bodies hoặc credentials.
- Rate-limit login, chống enumeration/brute force, phản hồi lỗi chung phù hợp.
- Không dùng service bind có quyền Domain Admin chỉ để lookup group.
- Tránh truyền user password qua một chuỗi microservices.

### 21.3. Trả lỗi phù hợp

Dành cho user:
- Sai credentials → thông báo chung, tránh lộ account existence.
- Identity chưa liên kết → hướng dẫn liên kết/đề nghị hỗ trợ, không tự ghép.
- Account disabled → thông báo truy cập bị từ chối theo policy.
- Directory timeout → lỗi dịch vụ tạm thời, không khẳng định password sai.
- Duplicate link → báo liên hệ admin/security support, không tiết lộ account ID của người khác.

Logs nội bộ nên phân biệt `DIRECTORY_NOT_FOUND`, `AUTH_BAD_CREDENTIALS`, `LINK_CONFLICT`, `ACCOUNT_DISABLED`, `DIRECTORY_TIMEOUT` và `AUTHZ_DENIED` nhưng không chứa bí mật.

## 22. Kiểm thử theo ba lớp

### 22.1. Directory lookup tests

| Test | Đầu vào | Kỳ vọng |
|---|---|---|
| L1 | User có entry | Trả đúng attrs theo allowlist, **không** tạo Authentication |
| L2 | User không có entry | Not found, không kết luận password sai |
| L3 | Filter match nhiều entries | Reject ambiguous nếu dùng identity resolution |
| L4 | UID có ký tự LDAP filter đặc biệt | Builder escape đúng, không injection |
| L5 | AD nested membership | Effective groups đúng policy |
| L6 | Directory account disabled | Status được trả, app enforce account policy |
| L7 | Directory unreachable | Timeout rõ, không cấp default admin |
| L8 | Read-only bind credentials | Chỉ có directory permissions được cấp |
| L9 | Query ngoài search base | Không leak dữ liệu ngoài scope |

### 22.2. Direct authentication tests

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| A1 | Username/password đúng, LDAP bind thành công | Authentication thành công theo account policy |
| A2 | Password sai | Bad credentials |
| A3 | Entry tồn tại nhưng password sai | **Không login** |
| A4 | User disabled/locked | Login bị từ chối |
| A5 | Không có LDAP TLS hoặc certificate không tin | Không disable TLS để bypass |
| A6 | Group loader timeout sau bind | Không tự cấp role admin |
| A7 | AD UPN vs uid khác nhau | Lookup/auth đúng scope và convention |
| A8 | LDAP compare salted-hash configuration | Kiểm compatibility, không dùng NoOp production |
| A9 | Form login rate limit | Chặn brute force và enumeration |
| A10 | User tìm thấy nhưng không có quyền app | Có thể authenticated nhưng 403 đúng policy |

### 22.3. Identity linking tests

| Test | Kịch bản | Kỳ vọng |
|---|---|---|
| I1 | Valid OIDC iss+sub, local session authenticated, explicit intent | Link thành công |
| I2 | External proof chưa được validate | Không link |
| I3 | Local session chưa authenticated/recent enough | Không link |
| I4 | External key đã linked cùng local ID | Idempotent/already linked |
| I5 | External key đã linked local ID khác | CONFLICT, không overwrite |
| I6 | Cùng sub nhưng issuer khác | Hai identity keys khác |
| I7 | Email trùng, sub khác | Không auto merge |
| I8 | Email verified nhưng local account chưa chứng minh | Không auto-link nhạy cảm |
| I9 | Account disabled | Không link/login |
| I10 | User từ tenant khác | Deny nếu ngoài policy |
| I11 | Concurrent link requests | Unique constraint chỉ cho một winner |
| I12 | Callback state/nonce/CSRF không khớp | Reject |
| I13 | OIDC UserInfo.sub khác ID Token.sub | Reject dữ liệu UserInfo |
| I14 | SAML transient NameID | Không dùng làm stable key trọn đời |
| I15 | Unknown issuer/realm | Deny |
| I16 | Unlink phương thức cuối | Theo account recovery policy, không lockout |
| I17 | JIT user first login | Tạo account mới với least privilege, audit |
| I18 | Duplicate AD object mapping | Reject ambiguous |
| I19 | Link revoked, login lại | Không tự re-enable nếu policy cấm |
| I20 | Provider đổi issuer/sub | Yêu cầu approved migration, không email-auto-link |

**Integration tests:** cần LDAP/AD hoặc test directory có data thực, IdP OIDC/SAML hay Kerberos KDC đúng protocol, Spring Security filter chain, HTTP session và database unique constraint. Mock principal đơn thuần không chứng minh authentication hoặc linking security.

## 23. Troubleshooting bằng cách xác định sai ở tầng nào

| Triệu chứng | Tầng khả nghi | Hướng xử lý |
|---|---|---|
| LDAP tìm thấy user nhưng form login báo sai password | Direct authentication | Kiểm bind DN, password, LDAP TLS, account flags |
| User login OIDC nhưng app không thấy user | Identity linking/lookup | Kiểm iss+sub, approved link và onboarding |
| User login thành công nhưng thiếu quyền | Authority lookup | Kiểm group-to-role mapping và tenant membership |
| LDAP search trả 2 entries | Directory resolution | Sửa unique key/search scope, reject ambiguity |
| SSO user liên kết sang account khác | Identity linking | Kiểm conflict/issuer/subject uniqueness, audit |
| User đổi email thì mất local account | Linking dùng email sai | Sử dụng stable provider subject |
| SAML transient NameID thay mỗi lần | Subject contract | Chọn stable attribute/persistent NameID theo IdP |
| OIDC token hợp lệ nhưng email local trùng | Link policy | Không auto merge, yêu cầu ownership proof |
| Kerberos principal đúng nhưng AD group chưa có | Directory/authority lookup | Realm/AD SID, nested groups, stale cache |
| Directory lookup không có password nhưng user hỏi form password | Thiết kế authentication | Phân biệt service read bind vs user bind |
| Password user đúng nhưng app 403 | Authorization | Không chữa bằng bypass roles |
| Group bị thu hồi nhưng session vẫn có quyền | Cache/session | Invalidate, policy-version TTL, entitlement check |
| Directory outage khiến login fail | Availability | Retry/backoff/circuit breaker, fail closed |
| Khác tenant nhưng email giống | Identity namespace | Issuer/realm/tenant mapping và unique links |
| LDAP injection báo search nhiều user | Query construction | Dùng escaped builder/parameters |
| Đăng nhập OAuth/OIDC yêu cầu password local bất ngờ | Provider selection | Kiểm Spring filters/chains, không thêm DaoAuthenticationProvider sai |
| CAS/Kerberos/SAML login thành công nhưng chưa link | Account mapping | Onboarding/JIT/linking rõ, không tự ghép email |

**Cách debug chuẩn:** *đã verify credential/protocol chưa?* → *directory identity resolution có một kết quả duy nhất không?* → *external identity link có approved target không?* → *local account active không?* → *group/role/tenant policy đúng không?* → *session/cache có stale data không?*.

## 24. Anti-patterns cần tránh

1. **Lookup = login:** LDAP search thấy email rồi tạo Authentication.
2. **Email = unique identity:** auto-link OIDC/SAML vào account local theo `mail` hoặc displayName.
3. **Realm bị bỏ:** Kerberos `alice@REALM-A` bị nhập nhằng với `alice@REALM-B`.
4. **Issuer do browser gửi:** lấy IdP issuer từ query header để dựng identity key.
5. **External proof giả:** tin claim tự parse chưa verify token/signature.
6. **UserInfo mix-up:** không kiểm UserInfo.sub trùng ID Token.sub.
7. **Direct bind qua plain LDAP:** gửi password mà không bảo vệ transport/trust.
8. **Directory admin bind:** dùng Domain Admin account chỉ để đọc memberships.
9. **LDAP filter string concat:** làm LDAP injection.
10. **Group text = app admin:** đặt mọi directory groups thành authorities.
11. **Auto-JIT với ROLE_ADMIN:** mọi external identity hợp lệ thành admin.
12. **Link without local proof:** dùng một IdP account sở hữu email giống người khác để chiếm local account.
13. **Không unique constraint:** hai link records cùng external key trỏ tới hai users.
14. **Link race overwrite:** thao tác UPDATE chuyển ownership khi đã linked người khác.
15. **No account lifecycle:** disabled local user vẫn được login vì external token valid.
16. **Trust all realms:** user từ partner realm tự lấy role nội bộ.
17. **Session stale forever:** AD revoke role nhưng Spring session không refresh.
18. **Ambiguous directory match:** lấy entry đầu tiên từ search trả nhiều records.
19. **Identity link = authorization:** có link thì tự xem mọi tenant.
20. **Unlink without recovery:** gỡ credential cuối cùng gây lockout tài khoản.

## 25. Checklist thiết kế và go-live

- [ ] Đã đặt tên rõ các service: DirectoryLookup, CredentialAuthenticator và IdentityLinkService.
- [ ] Directory lookup không tự tạo Spring Authentication.
- [ ] Direct LDAP bind/password compare được cấu hình đúng, có TLS và rate limits.
- [ ] Federation protocol (OIDC/SAML/Kerberos/CAS) được framework verify trước local mapping.
- [ ] Sử dụng OIDC iss+sub, không email làm unique key.
- [ ] SAML stable subject được thống nhất theo IdP contract.
- [ ] Kerberos principal/realm và AD object ID được bảo toàn.
- [ ] Local account luôn có stable internal ID không phụ thuộc email.
- [ ] Existing account linking yêu cầu local account proof + external proof.
- [ ] Link intent có state/nonce/CSRF, TTL và một lần sử dụng.
- [ ] Link có atomic database uniqueness, không tự overwrite conflict.
- [ ] Cross-tenant identity mapping có approval policy.
- [ ] JIT được tách khỏi linking và không tự tạo admin.
- [ ] User/group lookup dùng LDAP query builder/escaping, hạn chế search scope.
- [ ] Directory bind credentials dùng least privilege và secret manager.
- [ ] Account disabled/locked/revoked và group changes được áp vào authorization.
- [ ] Authorities được map từ allowlist/policy và kiểm ở resource-level.
- [ ] Caching/session revocation SLA đã được xác định.
- [ ] Không log password, raw tokens, keytab, LDAP secrets hay sensitive profile data.
- [ ] Có tests 0/1/n lookup, wrong password, invalid SSO proof, link conflicts, races, cross-realm/tenant.
- [ ] Có audit trace các thao tác link/unlink/migration với ID không tiết lộ secrets.
- [ ] Có UX riêng cho not found, bad credentials, unlinked identity, access denied và directory outage.

## 26. Câu hỏi ôn tập

1. **Directory lookup có xác minh browser là Alice không?** Không, chỉ tìm/đọc bản ghi.
2. **LDAP bind làm gì?** Directory kiểm credentials trong bind authentication.
3. **LDAP search và LDAP bind khác nhau thế nào?** Search đọc dữ liệu; bind xác thực quyền truy cập/credentials, và user-bind có thể được dùng để login.
4. **Spring LDAP bind có cần đọc password hash user từ directory không?** Không.
5. **Spring LDAP bind dùng UserDetailsService như DAO form login không?** Không theo cùng cách; dùng LdapAuthenticator và authority populator.
6. **LDAP password compare có giống bind không?** Không, là cơ chế xác thực khác.
7. **Sau OIDC login vì sao còn truy vấn AD?** Để lấy attrs/group/account status theo business policy.
8. **OIDC key nào ổn định để link identity?** Cặp trusted iss+sub.
9. **Email verified có đủ auto-link account local không?** Không mặc nhiên.
10. **SAML NameID có luôn ổn định không?** Không; transient hoặc format khác cần hợp đồng.
11. **Kerberos principal nên giữ gì?** Full principal và realm; có thể mapping AD stable ID.
12. **Có directory entry nhưng wrong password thì sao?** Direct auth fail.
13. **Có verified IdP identity nhưng chưa có link thì sao?** Onboarding/JIT theo policy hoặc deny, không auto-merge email.
14. **Một external identity có thể linked hai local users không?** Không nếu uniqueness policy là một-to-one; phải reject conflict.
15. **Tại sao linking cần xác minh hai phía?** Ngăn người sở hữu một external account chiếm local account của người khác.
16. **JIT có phải linking vào existing account không?** Không, thường tạo account mới với policy rõ.
17. **Làm sao tránh LDAP injection?** Dùng parameterized search/LDAP query builder, scope hạn chế.
18. **Tại sao lookup trả nhiều matches phải reject?** Vì không biết user object nào là đúng, dễ account confusion.
19. **Group membership có tự trở thành ROLE_ADMIN không?** Không; cần allowlist quyền ứng dụng.
20. **Role bị revoke có lập tức mất trong session không?** Không mặc định; cần TTL, invalidation hoặc live entitlement check.
21. **Direct auth bằng password có cần HTTPS không?** Có, cả client→app và app→directory được bảo vệ.
22. **Một service account dùng để read LDAP có chứng minh browser user không?** Không.
23. **OAuth2Login verified token có thay LDAP password bind không?** Có thể thay cơ chế login user; nhưng directory lookup sau đó vẫn riêng.
24. **Mục tiêu của bảng external_identity_links?** Nối stable external identity tới local user có kiểm soát.
25. **Nguyên tắc lớn nhất?** Tách rõ lookup, authentication và linking rồi thực thi authorization theo account/tenant/resource đã được kiểm.

## 27. Nguồn tham khảo chính thức

- Spring Security – LDAP Authentication, bind/password comparison và authorities populator: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security – ActiveDirectoryLdapAuthenticationProvider JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring LDAP – Reference, LdapTemplate và LdapQueryBuilder: https://docs.spring.io/spring-ldap/reference/
- Spring Security – OAuth2 Login Advanced Configuration, OidcUserService/authority mapping: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – UserDetailsService và DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security – OIDC/OAuth2 client: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Kerberos/SPNEGO: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- OpenID Connect Core – §5.7 `iss+sub`, §5.3.2 UserInfo sub matching: https://openid.net/specs/openid-connect-core-1_0.html
- LDAP Filter escaping – RFC 4515: https://www.rfc-editor.org/rfc/rfc4515
- OWASP – LDAP Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Tổng kết:** Directory lookup trả về thông tin về một identity, **không chứng minh người gọi sở hữu identity**. Direct authentication kiểm credential bằng LDAP bind, password comparison, local password encoder hoặc một verifier tương ứng. Identity linking là quyết định gắn external identity đã được xác thực với local account, phải dựa vào stable provider-scoped identifier, xác minh quyền sở hữu hai phía, uniqueness/transaction và audit. Trong hệ Spring Security federation, hãy tách rành mạch: **protocol verification → trusted principal → directory lookup nếu cần → approved identity link/local account → role/tenant/resource authorization**. Sự phân tách đó ngăn sai lầm nghiêm trọng như LDAP lookup-as-login, email auto-link dẫn tới account takeover và cấp quyền ứng dụng chỉ vì IdP authentication thành công.
