# Phương án đăng nhập dự phòng mà không hạ thấp chính sách xác thực

> **Module:** Spring Security – federation. **Chủ đề cha:** Tích hợp Kerberos. Bài viết hướng dẫn thiết kế đăng nhập dự phòng khi Kerberos/SPNEGO không khả dụng nhưng không giảm mức bảo đảm xác thực, không bỏ qua MFA, không tự động hạ cấp sang NTLM/Basic và không làm sai ánh xạ danh tính, quyền nghiệp vụ hay tenant.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Kerberos/SPNEGO sử dụng HTTP `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`, Kerberos service principal, keytab và xác minh GSS-API như thế nào.
2. Phân biệt **browser không hỗ trợ SPNEGO**, **KDC/DNS/VPN unavailable**, **sai SPN/keytab/clock skew**, **vé Kerberos không hợp lệ**, **tài khoản bị vô hiệu** và **thiếu MFA/step-up**.
3. Chọn các phương án fallback đã được duyệt: OIDC Authorization Code với MFA/passkey, SAML2 với chính sách tương đương hoặc LDAP/password **kèm MFA bắt buộc** khi policy cho phép.
4. Thiết kế một bảng **resource → assurance requirement → accepted authentication evidence → local authorization** dùng chung cho mọi phương thức đăng nhập.
5. Tránh xem “có Kerberos ticket” là bằng chứng MFA tự động, hoặc “OIDC login thành công” là bằng chứng phishing resistance.
6. Sử dụng `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `AuthenticationProvider`, `SecurityFilterChain` và `oauth2Login` đúng nhiệm vụ, không xây provider giả xác minh.
7. Phân biệt trang lựa chọn đăng nhập dự phòng với một cơ chế cấp quyền tự động; xử lý chính xác HTTP 401/302/403 và browser không gửi token.
8. Bảo vệ account linking giữa Kerberos realm/principal và OIDC `issuer + sub`, session fixation, CSRF, redirect URI và yêu cầu tái xác thực.
9. Viết và chạy chương trình Java 17 phân loại kết quả chính sách với stdout xác định; xem Spring Boot 3.3 module OIDC fallback không tự cấp quyền admin.
10. Thiết kế vận hành khi KDC/IdP outage, keytab rotation, break-glass, logging, metrics, cảnh báo và rollback.
11. Kiểm thử trường hợp attacker cố ép downgrade, token giả, role bị thu hồi, user không đạt ACR, ACR lỗi, đa tenant và browser không hỗ trợ Negotiate.

**Phạm vi:** Java Servlet, Kerberos V5/SPNEGO và Spring Security. Bài dùng Java 17; code Spring Boot 3.3.x / Spring Security 6.3.x là baseline học tập. Spring Security Kerberos là **extension riêng**, cần xác minh phiên bản phù hợp Jakarta Servlet trước khi tích hợp với Boot 3.x. **Đây không phải hướng dẫn bỏ qua xác thực khi KDC lỗi.**

## 2. Một hệ thống, nhiều thiết bị, cùng chính sách bảo mật

Giả sử Orders Portal có các đường truy cập:

| Tài nguyên | Mức xác thực cần có | Quyền ứng dụng cần có |
| --- | --- | --- |
| `GET /me` | Identity đã được xác thực bằng nguồn tin cậy, tài khoản ACTIVE. | User được phép truy cập Portal. |
| `GET /orders` | Authentication phù hợp chính sách cơ bản. | `APP_ORDER_READ` và đúng tenant. |
| `POST /orders/{id}/approve` | MFA phù hợp chính sách tổ chức, thời hạn không quá giới hạn. | `APP_ORDER_APPROVE` và đúng order owner/tenant. |
| `GET /admin/export` | Phương thức **phishing-resistant**, MFA và auth freshness theo chính sách đã được bảo mật phê duyệt. | `APP_ADMIN_EXPORT`, approval và tài khoản không bị khóa. |
| `GET /public/health` | Không cần end-user login. | Không để lộ secret hay dữ liệu nội bộ. |

Người dùng A truy cập từ laptop domain-joined và nhận một Kerberos ticket hợp lệ. Người dùng B ở ngoài domain không gửi được SPNEGO token. Quản trị viên C có thể dùng Kerberos SSO nhưng cần bước MFA mới để xuất dữ liệu nhạy cảm.

**Thiết kế sai:** Khi không thấy `Authorization: Negotiate`, tự hiển thị một form chỉ username/password không có MFA và cho mọi người truy cập cả `/admin/export`.

**Thiết kế đúng:** Người dùng không dùng được SPNEGO có lựa chọn đến **IdP OIDC/SAML đã được phê duyệt**, nhận authentication mới qua protocol chuẩn, rồi ứng dụng vẫn so khớp local account, permissions, tenant và assurance của từng resource. Với resource yêu cầu MFA chống phishing, **chỉ** phương thức chứng minh được yêu cầu mới được chấp nhận.

**Quan trọng:** Kerberos, OIDC và SAML mô tả cách chuyển và kiểm chứng danh tính. Chúng **không tự** xác định phương thức nào luôn mạnh hơn. Mức bảo đảm phụ thuộc authenticator cụ thể, IdP policy, MFA, thiết bị, freshness và kiểm chứng của SP.

## 3. Luồng Kerberos/SPNEGO cần hiểu trước khi xây fallback

~~~text
Browser/domain device        Portal SPNEGO                 Kerberos KDC
       |                           |                            |
       | GET /orders               |                            |
       |-------------------------->|                            |
       |<-- 401 WWW-Authenticate: Negotiate                      |
       |                           |                            |
       |-- obtain service ticket ------------------------------->|
       |<---------------------- Kerberos ticket -----------------|
       |                           |                            |
       | GET /orders               |                            |
       | Authorization: Negotiate <opaque-token>                 |
       |-------------------------->|                            |
       |                           | GSS-API acceptSecContext   |
       |                           | service keytab/realm/SPN   |
       |                           | local identity mapping     |
       |                           | Spring authorization       |
       |<-- 200 or 403 ------------|                            |
~~~

Máy chủ dịch vụ có SPN dạng:

~~~text
HTTP/portal.example.com@EXAMPLE.COM
~~~

Browser lấy service ticket cho đúng principal; `SpnegoAuthenticationProcessingFilter` nhận token từ header `Authorization: Negotiate` và gọi `AuthenticationManager`. Provider xác minh vé thực sự bằng cấu hình tin cậy (service account/keytab/realm), rồi Spring tạo `Authentication`; ứng dụng thực hiện local authorization.

**Không bao giờ** coi một HTTP header `Authorization: Negotiate` có giá trị bất kỳ là authentication proof. Ticket phải được giải mã/xác minh bằng provider, có kiểm tra nguồn, mục tiêu, thời gian và các ràng buộc của Kerberos protocol.

### 3.1. Tài liệu extension Spring liên quan

- `SpnegoEntryPoint` gửi challenge `WWW-Authenticate: Negotiate`; có thể được cấu hình forward tới một URL chứa lựa chọn form/OIDC fallback.
- `SpnegoAuthenticationProcessingFilter` nhận header Negotiate và gọi `AuthenticationManager`. Nó có `failureHandler` và `successHandler`.
- `KerberosServiceAuthenticationProvider` / `SunJaasKerberosTicketValidator` thường xử lý service tickets bằng JAAS/JGSS theo extension.
- `KerberosAuthenticationProvider` có thể hỗ trợ một kiểu xác thực Kerberos với username/password trong các cấu hình khác, **không tự tương đương MFA**.
- Tất cả các lớp Kerberos trên thuộc **spring-security-kerberos extension**, không có sẵn chỉ với Spring Boot starter security.

**Một khác biệt thực tế:** theo Javadoc của extension, nếu browser **không gửi token** thì filter có thể **không gọi** failure handler, bởi không có Kerberos authentication attempt phía server. Vì thế fallback không được thiết kế dựa hoàn toàn vào một nhánh catch exception.

## 4. Phân loại lỗi trước khi quyết định hiện fallback

| Phân loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| `NO_NEGOTIATE_CREDENTIAL` | Browser hoặc thiết bị không gửi header Negotiate. | Cho lựa chọn OIDC/SAML; **chưa có Authentication**. |
| `BROWSER_NOT_CONFIGURED` | Browser chưa allowlist intranet URL, proxy chặn challenge. | Hướng dẫn hoặc IdP dự phòng, không tự cấp session. |
| `KDC_UNAVAILABLE` | DNS/VPN/KDC outage, browser không lấy được ticket. | Ghi sự cố, cho fallback được duyệt nếu IdP còn hoạt động. |
| `SPN_OR_KEYTAB_FAILURE` | SPN sai/trùng, kvno lệch, keytab cũ, key rotation lỗi. | Sửa infrastructure, không tắt Kerberos validation. |
| `CLOCK_SKEW` | Giờ client/KDC/service khác xa. | Sửa NTP/time sync, không gia hạn ticket tùy tiện. |
| `INVALID_NEGOTIATE_TOKEN` | Token giả, sai integrity, replay hoặc không thuộc realm tin cậy. | Reject và ghi audit/rate limit; không coi là user verified. |
| `UNKNOWN_REALM` | Ticket từ realm chưa được phép. | Reject, không tự thêm trust. |
| `ACCOUNT_DISABLED` | IdP/local account bị khóa/hết hiệu lực. | DENY trong mọi phương thức. |
| `NO_ACCOUNT_LINK` | Kerberos hoặc OIDC principal chưa linked local account. | DENY/provisioning; không auto-create admin. |
| `MFA_REQUIRED` | Authentication hợp lệ nhưng resource đòi MFA. | Step-up qua IdP đã duyệt, không giảm yêu cầu. |
| `PHISHING_RESISTANCE_REQUIRED` | Có OTP nhưng policy đòi passkey/FIDO2 tương đương. | Deny/step-up mạnh hơn. |
| `FALLBACK_IDP_FAILURE` | OIDC issuer/token/signature/nonce/ACR không hợp lệ. | Reject, không mở Kerberos bypass. |
| `ALL_APPROVED_METHODS_UNAVAILABLE` | Cả Kerberos và IdP dự phòng đều outage. | Fail closed, trang hỗ trợ, quy trình break-glass riêng. |

**Một outage chỉ cho phép thay luồng điều hướng sang phương thức được duyệt, không cho phép giảm độ tin cậy của bằng chứng.**

### 4.1. HTTP 401, 302, 403 và 5xx không đồng nghĩa

- **401 + Negotiate:** server yêu cầu browser gửi chứng cứ Integrated Windows Authentication; chưa chứng minh user identity.
- **302 tới IdP OIDC/SAML:** bắt đầu một lần đăng nhập mới, **không** phải bước cấp role.
- **403:** đã có identity nhưng thiếu quyền hoặc assurance, cần step-up hoặc dừng hành động.
- **5xx:** backend/KDC/service configuration failure cần vận hành xử lý, không chuyển thành 200.
- **200:** chỉ khi authentication và authorization thích hợp đều thành công.

Machine clients có thể cần `401/403`/OAuth2 resource-server token hoặc mTLS, không nên bị 302 vòng lặp tới trang login người dùng.

## 5. Bất biến an toàn: fallback không được hạ chuẩn

### 5.1. Mọi đường login đều cần bằng chứng độc lập

Sai:

~~~java
// SAI: lỗi Kerberos không cho phép tự tạo user mặc định.
try {
    return kerberosProvider.authenticate(request);
} catch (Exception ex) {
    return new MyAdminAuthentication("fallback-user");
}
~~~

Đúng: thất bại → trả challenge hoặc trang lựa chọn; chỉ tạo Authentication khi **một provider khác thực sự xác minh** chứng cứ mới.

### 5.2. Không tự động giảm MFA/step-up

Nếu `/admin/export` đòi MFA và phishing resistance, một form password-only **không đáp ứng** chỉ vì Kerberos thất bại. Nếu OIDC IdP không trả đúng evidence về method/freshness, chặn resource dù login cơ bản đã thành công.

### 5.3. Không lẫn authentication với authorization

Kerberos ticket hoặc OIDC ID Token xác minh danh tính. Các quyền `APP_ORDER_APPROVE`, `APP_ADMIN_EXPORT` và tenant ownership là quyết định nghiệp vụ riêng của ứng dụng, không cấp chỉ vì issuer/realm đúng.

### 5.4. Không hạ cấp protocol tự động

Một số platform dùng “Negotiate” có thể chuyển sang NTLM nếu Kerberos không hoạt động. **Đừng suy chỉ từ tên header Negotiate rằng phiên đã được xác minh bằng Kerberos.** NTLM và HTTP Basic có trade-offs bảo mật khác; không tự bật chúng làm phương án “chạy được là được”. Cần network/OS controls, logs và audit NTLM theo chính sách.

### 5.5. Session sau fallback vẫn phải tuân một chính sách

Cần chống session fixation, CSRF cho browser forms, cookie Secure/HttpOnly/SameSite, thời hạn session, account revocation và step-up freshness như những phiên Kerberos khác. Không cho một fallback session sống lâu hơn vô hạn chỉ vì nó dùng OIDC.

## 6. Các phương án dự phòng và điều kiện sử dụng

| Phương án | Tình huống sử dụng | Điều kiện bắt buộc | Cảnh báo |
| --- | --- | --- | --- |
| OIDC Authorization Code + MFA/passkey | Device không domain, KDC/Negotiate lỗi. | IdP issuer allowlist, TLS, PKCE/state/nonce, token validation, ACR/AMR policy, identity linking. | OIDC protocol **không mặc định chứng minh MFA**. |
| SAML2 SSO qua IdP có MFA | Doanh nghiệp dùng SAML IdP được quản trị. | Signed assertion, Issuer, Audience, Recipient, InResponseTo, AuthnContext, local account. | Không bỏ signature validation để cứu lỗi. |
| LDAP/AD password + second factor | Legacy exception đã được phê duyệt. | LDAPS/TLS, MFA, rate limit, lockout, hardening, session policy. | LDAP bind/password only không tự đủ cho sensitive routes. |
| Passkey/FIDO2 qua IdP | Phishing-resistant MFA và thiết bị hỗ trợ. | Đúng RP origin, authenticator enrollment, assertion được IdP validate, ACR policy. | Không tin browser tự tuyên bố đã dùng passkey. |
| Step-up OIDC/SAML | Kerberos hợp lệ cho dashboard nhưng không đủ approve/admin. | Đúng user, freshness, challenge/ACR yêu cầu, local role và action permission. | Step-up cho user khác không được giữ quyền user cũ. |
| Break-glass riêng | KDC và IdP outage, cần tác vụ khôi phục khẩn cấp. | Vault, approval, hardware MFA, least privilege, TTL ngắn, audit, hậu kiểm. | Không phải nút “bỏ MFA” mở cho mọi user. |

**Không xếp hạng assurance chỉ theo tên Kerberos/OIDC/SAML.** Cần đánh giá authenticator cụ thể và trust/evidence theo policy.

## 7. Chính sách theo resource, không theo lỗi của phương thức đăng nhập

~~~text
GET /resource
   |
   +-- no verified authentication?
   |       |
   |       +-- SPNEGO suitable? -> challenge Negotiate
   |       |                            |
   |       |                            +-- valid ticket -> verified identity
   |       |                            +-- unsupported  -> login choice
   |       |
   |       +-- user chooses approved IdP -> OIDC/SAML
   |                                       -> validated identity
   |
   +-- verified identity
           |
           +-- link to SAME active local account
           |
           +-- load local roles, tenant, device policy
           |
           +-- check resource assurance requirement
                    |
                    +-- sufficient -> authorize resource
                    |
                    +-- insufficient -> step-up or DENY
~~~

Không có cạnh “token invalid → grant admin” hoặc “IdP down → disable MFA”. Hiển thị trang lựa chọn fallback là quyết định UX, **không thay đổi** chính sách tài nguyên.

### 7.1. Trang lựa chọn hợp lệ

Một trang `/login-choice` được permitAll có thể có:
- “Thử lại đăng nhập tích hợp” tới route Negotiate đã định sẵn;
- “Đăng nhập bằng tài khoản tổ chức” tới `/oauth2/authorization/workforce` của IdP đã được cấu hình;
- “Hướng dẫn kết nối VPN hoặc liên hệ hỗ trợ” không thu mật khẩu trực tiếp.

Không lấy `issuer`, `casServer`, `returnTo` từ query chưa tin rồi chuyển tới URL tùy ý. Nếu cần quay lại trang ban đầu, chỉ cho redirect relative path allowlisted hoặc SavedRequest hợp lệ cùng origin.

### 7.2. Không tạo vòng lặp challenge

Browser có thể từ chối 401 Negotiate và không phát token. Nếu `/login-choice` lại bị SPNEGO entry point bắt, user sẽ lặp 401/forward vô hạn. Trang fallback, OIDC authorization endpoint và callback phải được chain/matcher phù hợp để không bị chặn nhầm.

## 8. NIST AAL, MFA và phishing resistance

NIST SP 800-63B-4 quy định các mức **Authenticator Assurance Level (AAL)** và tính chất của authenticator. Mức AAL không được xác định chỉ bằng tên giao thức được dùng trong app.

### 8.1. Kerberos ticket và MFA

Một Kerberos service ticket hợp lệ chứng minh điều được **Kerberos/KDC/acceptor** xác minh trong môi trường tương ứng; nó **không tự** xác nhận user vừa thực hiện MFA, dùng thiết bị compliant hoặc chứng thực chống phishing.

Nếu tổ chức muốn xem một phiên Kerberos có MFA, cần **bằng chứng bổ sung đã được tin** từ IdP/device/enterprise authentication ceremony, có freshness và chính sách mapping. Không gán `mfa=true` vì browser không hiện password prompt.

### 8.2. OIDC ACR/AMR và auth_time

Trong OIDC, `acr` và `amr` có thể giúp mô tả authentication context/method, `auth_time` chỉ thời điểm xác thực. Nhưng:

1. ID Token phải được kiểm tra signature, `iss`, `aud`, `exp`, `nonce` và `state` của authorization flow theo framework.
2. `acr` values phải được IdP và ứng dụng thỏa thuận rõ: không có ý nghĩa toàn cầu “giá trị nào cũng tương đương AAL2”.
3. `amr` không tự là bằng chứng một authenticator chống phishing đúng chuẩn; OTP thủ công thường **không phishing-resistant**.
4. Resource đòi freshness phải kiểm tra `auth_time` thật, không dùng thời gian tạo local session thay thế.
5. Nếu claim vắng/sai hoặc IdP không có hợp đồng đảm bảo, **fail closed** với resource nhạy cảm.
6. Một step-up flow không được đổi subject sang tài khoản khác mà vẫn giữ các quyền cũ.

Ví dụ tên policy nội bộ:

~~~text
BASIC:
    verified_identity + active_local_account

WORKFORCE_MFA:
    BASIC + verified_approved_MFA_evidence

PHISHING_RESISTANT_FRESH:
    BASIC + approved_phishing_resistant_authenticator
    + verified_auth_time_within_window
    + high_risk_authorization
~~~

Đây là **policy nội bộ minh họa**, không phải chuỗi `acr` chuẩn mà bất kỳ IdP nào cũng phát.

## 9. Ma trận quyết định khi gặp sự cố

| Tình huống | Dashboard cơ bản | Chức năng yêu cầu MFA/phishing resistance |
| --- | --- | --- |
| Browser không thể Negotiate, OIDC hoạt động | Cho OIDC nếu identity/local account hợp lệ. | Chỉ cho nếu IdP evidence đủ đúng policy. |
| KDC outage, IdP OIDC độc lập vẫn hoạt động | Có thể fallback. | Yêu cầu MFA/freshness như bình thường. |
| SPN/keytab cấu hình sai | Incident; fallback nếu được duyệt. | Không bỏ GSS check; IdP đủ assurance mới được phép. |
| Token Negotiate sai integrity hoặc giả | Reject/audit. | Reject; không tự cấp role/giảm authentication. |
| Account disabled/locked | DENY. | DENY. |
| Identity chưa được linked | DENY/provisioning. | DENY, không tự cấp quyền admin. |
| Kerberos hợp lệ nhưng không có MFA evidence | Chấp nhận nếu BASIC policy cho phép. | Challenge step-up hoặc DENY. |
| OIDC password only, thiếu assurance claim | Có thể đủ BASIC theo policy. | Không đủ: DENY/step-up. |
| OIDC assertion sai issuer/signature/nonce | Reject. | Reject. |
| Cả KDC và IdP down | Không có login mới. | Không giảm chính sách; break-glass quy trình riêng. |
| Session cũ còn hiệu lực nhưng local quyền đã bị thu hồi | Deny theo revocation policy. | Deny, không coi session trước là quyền vĩnh viễn. |

## 10. Java 17: bộ quyết định policy có stdout xác định

Ví dụ này chạy offline và nhận **bằng chứng giả lập đã được validator kiểm chứng**. Trong thực tế các cờ `verified`, `mfa`, `phishingResistant`, `fresh` không bao giờ được lấy từ HTTP query/body do client tùy ý gửi.

### 10.1. `KerberosFallbackPolicyDemo.java`

~~~java
public final class KerberosFallbackPolicyDemo {

    enum Method {
        KERBEROS, OIDC, EMERGENCY
    }

    enum Requirement {
        BASIC, MFA, PHISHING_RESISTANT_FRESH
    }

    enum Decision {
        ALLOW,
        DENY_UNVERIFIED,
        DENY_DISABLED,
        DENY_UNLINKED,
        DENY_PRIVILEGE,
        STEP_UP_MFA,
        STEP_UP_PHISHING_RESISTANT,
        STEP_UP_FRESH
    }

    record Evidence(
        Method method,
        boolean verified,
        boolean activeAccount,
        boolean linkedIdentity,
        boolean privileged,
        boolean mfa,
        boolean phishingResistant,
        boolean fresh) {
    }

    static Decision decide(Evidence e,
                           Requirement required,
                           boolean privilegedResource) {

        if (!e.verified()) {
            return Decision.DENY_UNVERIFIED;
        }
        if (!e.activeAccount()) {
            return Decision.DENY_DISABLED;
        }
        if (!e.linkedIdentity()) {
            return Decision.DENY_UNLINKED;
        }
        if (privilegedResource && !e.privileged()) {
            return Decision.DENY_PRIVILEGE;
        }

        if (required == Requirement.BASIC) {
            return Decision.ALLOW;
        }
        if (!e.mfa()) {
            return Decision.STEP_UP_MFA;
        }
        if (required == Requirement.MFA) {
            return Decision.ALLOW;
        }
        if (!e.phishingResistant()) {
            return Decision.STEP_UP_PHISHING_RESISTANT;
        }
        if (!e.fresh()) {
            return Decision.STEP_UP_FRESH;
        }
        return Decision.ALLOW;
    }

    static void show(String name, Evidence evidence,
                     Requirement required, boolean privileged) {
        System.out.println(name + "=" +
            decide(evidence, required, privileged));
    }

    public static void main(String[] args) {
        Evidence kerberos = new Evidence(
            Method.KERBEROS, true, true, true,
            false, false, false, false);

        Evidence oidcMfa = new Evidence(
            Method.OIDC, true, true, true,
            false, true, false, true);

        Evidence oidcStrong = new Evidence(
            Method.OIDC, true, true, true,
            true, true, true, true);

        Evidence oidcStale = new Evidence(
            Method.OIDC, true, true, true,
            true, true, true, false);

        Evidence forged = new Evidence(
            Method.KERBEROS, false, true, true,
            true, true, true, true);

        Evidence disabled = new Evidence(
            Method.OIDC, true, false, true,
            true, true, true, true);

        Evidence unlinked = new Evidence(
            Method.OIDC, true, true, false,
            true, true, true, true);

        Evidence missingRole = new Evidence(
            Method.OIDC, true, true, true,
            false, true, true, true);

        Evidence emergency = new Evidence(
            Method.EMERGENCY, true, true, true,
            true, false, false, true);

        show("kerberosDashboard", kerberos,
            Requirement.BASIC, false);
        show("kerberosNeedsMfa", kerberos,
            Requirement.MFA, false);
        show("oidcDashboard", oidcMfa,
            Requirement.BASIC, false);
        show("oidcMfa", oidcMfa,
            Requirement.MFA, false);
        show("oidcNotPhishingResistant", oidcMfa,
            Requirement.PHISHING_RESISTANT_FRESH, false);
        show("strongAdmin", oidcStrong,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("staleAdmin", oidcStale,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("forgedToken", forged,
            Requirement.BASIC, false);
        show("disabledAccount", disabled,
            Requirement.BASIC, false);
        show("unlinkedIdentity", unlinked,
            Requirement.BASIC, false);
        show("missingRole", missingRole,
            Requirement.PHISHING_RESISTANT_FRESH, true);
        show("breakGlassWeak", emergency,
            Requirement.PHISHING_RESISTANT_FRESH, true);
    }
}
~~~

### 10.2. Chạy

~~~bash
javac --release 17 KerberosFallbackPolicyDemo.java
java KerberosFallbackPolicyDemo
~~~

**Stdout chính xác:**

~~~text
kerberosDashboard=ALLOW
kerberosNeedsMfa=STEP_UP_MFA
oidcDashboard=ALLOW
oidcMfa=ALLOW
oidcNotPhishingResistant=STEP_UP_PHISHING_RESISTANT
strongAdmin=ALLOW
staleAdmin=STEP_UP_FRESH
forgedToken=DENY_UNVERIFIED
disabledAccount=DENY_DISABLED
unlinkedIdentity=DENY_UNLINKED
missingRole=DENY_PRIVILEGE
breakGlassWeak=STEP_UP_MFA
~~~

**Ý nghĩa:** Bằng chứng chưa verify bị từ chối đầu tiên, account disabled bị chặn ở mọi phương thức, quyền local được kiểm tra độc lập, MFA không tự thành phishing resistance, và một break-glass chỉ password không tự vượt policy.

`Method` chỉ là nhãn về nguồn; chương trình **không cho Method=KERBEROS hay OIDC tự tăng assurance**. Trong production phải sinh `Evidence` từ một Kerberos acceptor/provider hoặc OIDC/SAML verifier thực sự, và gắn nguồn IdP/realm + subject, freshness, device policy đã xác thực. Không sử dụng code mô phỏng làm bộ xác thực thực tế.

## 11. Spring Security Kerberos: extension points cần cấu hình

| Thành phần | Vai trò | Sai lầm cần tránh |
| --- | --- | --- |
| `SpnegoEntryPoint` | Phát challenge HTTP Negotiate; có overload cho fallback page. | Nghĩ forward tới trang login là đã authenticate. |
| `SpnegoAuthenticationProcessingFilter` | Nhận và xử lý header Negotiate, gọi manager/provider. | Coi token có prefix “Negotiate” là valid. |
| `KerberosServiceAuthenticationProvider` | Provider xác minh Kerberos service ticket. | Thay bằng provider luôn trả success. |
| `SunJaasKerberosTicketValidator` | Kerberos acceptor dùng JAAS/keytab theo implementation. | Bỏ service ticket checks để “fix keytab”. |
| `KerberosAuthenticationProvider` | Một Kerberos provider khác, không mặc định là MFA. | Gộp với service ticket provider mà không hiểu flow. |
| `AuthenticationManager` | Ủy quyền cho provider phù hợp loại token. | Cho UsernamePassword provider chấp nhận Negotiate bytes. |
| `SecurityFilterChain` | Định tuyến paths và filter order. | Bảo vệ nhầm OIDC callback bằng Negotiate challenge. |
| `oauth2Login` | OIDC login qua IdP được duyệt. | Tin browser tự nêu issuer/ACR. |
| `saml2Login` | SAML2 fallback nếu doanh nghiệp dùng SAML IdP. | Bỏ signature/AuthnContext checks. |
| `AuthorizationManager` | Gate assurance/permission cho resource. | Chỉ dựa `authenticated()` cho endpoint nhạy cảm. |

### 11.1. `SpnegoEntryPoint` là điều hướng, không phải authentication policy

Spring Security Kerberos Javadoc hỗ trợ cấu hình trang fallback:

~~~java
// MẢNH cấu hình: import và bean phụ thuộc extension/version thật.
SpnegoEntryPoint entryPoint =
    new SpnegoEntryPoint("/login-choice");
~~~

Với overload này, entry point có thể phát `401 Negotiate` đồng thời forward tới trang login tùy version/browser; **không giả định** một redirect 302 xảy ra với mọi client. Cần test browser Windows/macOS/Linux và proxy.

Nếu người dùng không gửi token, `SpnegoAuthenticationProcessingFilter.failureHandler` có thể không được gọi. Cần một trang `/login-choice` công khai và link OIDC thay thế, không chỉ viết một catch block.

### 11.2. Failed Negotiate không tự tạo phiên fallback

~~~java
// MẢNH wiring: filter đã được khởi tạo, đúng version.
spnegoFilter.setFailureHandler((request, response, ex) -> {
    // Chỉ ghi loại lỗi; KHÔNG log raw Negotiate token.
    response.sendError(
        401, "Integrated login failed; choose approved sign-in");
});
~~~

Một failure handler tốt **không**:
- Gán `ROLE_USER` hoặc `ROLE_ADMIN`;
- Đặt `SecurityContext` authenticated với user default;
- Bỏ qua account disabled khi network lỗi;
- Redirect tới arbitrary `returnTo`;
- Bật Basic/NTLM không được quản trị duyệt.

### 11.3. Mẫu SecurityFilterChain theo nhóm client

~~~text
@Order(1): /api/**
  -> OAuth2 Resource Server JWT/opaque token hoặc mTLS
  -> STATELESS, 401/403; không HTML login page

@Order(2): /oauth2/**, /login/oauth2/**, /login-choice
  -> callback/entry routes OIDC, không bị SPNEGO challenge chiếm

@Order(3): /**
  -> browser Kerberos filter + approved OIDC fallback
  -> HttpSession/SecurityContext, CSRF, session fixation
  -> resource assurance authorization
~~~

Đây là **sơ đồ kiến trúc**, không phải Java security config tự dựng ba chains. Trong Spring Security, matcher đầu tiên phù hợp sẽ chọn một `SecurityFilterChain`. Nếu chain callback OIDC bị chặn trước, fallback hỏng dù IdP xác thực thành công. Nếu API dùng browser chain, machine client nhận 302 HTML.

**Nên kiểm thử toàn bộ callback/saved request/redirect paths**, không chỉ đường `/orders`. Tài khoản cần step-up ở `/admin/**` không được dùng một route khác để bỏ qua `AuthorizationManager`/method-security gate.

## 12. Spring Boot 3.3: module OIDC dự phòng có kiểm tra assurance

Dự án sau là **module fallback OIDC** đủ cấu trúc để cấu hình với IdP thật; nó chưa gắn Kerberos extension vào cùng chain. Việc tách riêng giúp không giả vờ có một dependency Kerberos/Jakarta đã được kiểm chứng trong khi chỉ cần minh họa **nguyên tắc fallback không cấp admin quyền tự động**.

### 12.1. Cấu trúc

~~~text
kerberos-oidc-fallback/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/fallback/
    │   ├── FallbackApplication.java
    │   ├── SecurityConfig.java
    │   └── InfoController.java
    └── resources/
        └── application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'kerberos-oidc-fallback'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 12.2. `FallbackApplication.java`

~~~java
package com.example.fallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }
}
~~~

### 12.3. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: "${WORKFORCE_OIDC_CLIENT_ID}"
            client-secret: "${WORKFORCE_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          workforce:
            issuer-uri: "${WORKFORCE_OIDC_ISSUER_URI}"

app:
  security:
    admin-required-acr: "${WORKFORCE_ADMIN_ACR}"

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Các biến môi trường phải đến từ cấu hình được quản trị. `WORKFORCE_ADMIN_ACR` là giá trị **chính xác** do IdP và security team quy ước cho một phương thức đã được kiểm chứng đáp ứng yêu cầu. Không đoán ACR chỉ vì tên chứa `mfa`.

### 12.4. `SecurityConfig.java`

~~~java
package com.example.fallback;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            @Value("${app.security.admin-required-acr}")
            String requiredAcr) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-choice", "/error")
                    .permitAll()
                .requestMatchers("/admin/**").access(
                    (authenticationSupplier, context) -> {
                        Authentication authentication =
                            authenticationSupplier.get();
                        return new AuthorizationDecision(
                            adminAllowed(authentication, requiredAcr)
                        );
                    }
                )
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login-choice")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            .build();
    }

    static boolean adminAllowed(
            Authentication authentication,
            String requiredAcr) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        if (!(authentication instanceof OAuth2AuthenticationToken oidc)
                || !(oidc.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        // ACR là contract IdP; không phải do browser nhập.
        if (requiredAcr.isBlank()
                || !requiredAcr.equals(
                    user.getIdToken().getClaimAsString("acr"))) {
            return false;
        }

        // Quyền nội bộ vẫn bắt buộc; demo không cấp role này.
        return authentication.getAuthorities().stream().anyMatch(
            authority ->
                "APP_ADMIN_EXPORT".equals(authority.getAuthority())
        );
    }
}
~~~

**Code này có chủ đích DENY admin theo mặc định**: Spring OAuth login không tự phát `APP_ADMIN_EXPORT` trong dự án mẫu. Production phải map local user/roles qua nguồn được duyệt **và** bổ sung kiểm tra account disabled, tenant, `auth_time` freshness, device compliance, transaction-level checks. Chỉ check ACR và role **chưa đủ** để tuyên bố toàn bộ policy PHISHING_RESISTANT_FRESH đã được thực thi.

Nếu IdP không trả `acr` trong ID Token được Spring validate, admin bị chặn. Không nên “fix” bằng cách đọc `?acr=strong` từ query hoặc mặc định ACR thành mạnh. Token validation, issuer, audience, nonce, state và PKCE cần được xác nhận theo cấu hình OIDC/framework hiện hành.

### 12.5. `InfoController.java`

~~~java
package com.example.fallback;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InfoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "loginUrl", "/oauth2/authorization/workforce",
            "note", "Approved organizational identity provider");
    }

    @GetMapping("/login-choice")
    public Map<String, String> loginChoice() {
        return Map.of(
            "loginUrl", "/oauth2/authorization/workforce",
            "note", "Choose approved fallback sign-in");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }

    @GetMapping("/admin/status")
    public Map<String, String> adminStatus() {
        return Map.of("result", "Admin policy gate passed");
    }
}
~~~

### 12.6. Chạy và giới hạn

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell có thể dùng `.\gradlew.bat bootRun`. Chuẩn bị IdP OIDC thật với issuer URL, HTTPS, client ID/secret và redirect URI public đã đăng ký:

~~~text
WORKFORCE_OIDC_CLIENT_ID=<registered-client>
WORKFORCE_OIDC_CLIENT_SECRET=<secret-from-vault>
WORKFORCE_OIDC_ISSUER_URI=https://idp.partner.example/realms/workforce
WORKFORCE_ADMIN_ACR=urn:example:acr:phishing-resistant
~~~

Đây là giá trị minh họa; không có IdP thật ở host `.example` nên lệnh không tự chứng minh login end-to-end.

Kỳ vọng: `/oauth2/authorization/workforce` bắt đầu OIDC redirect; callback `/login/oauth2/code/workforce` được Spring xử lý; `/me` yêu cầu login; `/admin/status` bị từ chối nếu không có **cả** ACR đúng và local authority. Role admin **không** được cấp trong demo nên mặc định bị chặn, thể hiện fail-closed.

**Không kết luận chỉ vì dự án khởi động thành công rằng MFA, PKCE, local account linking, freshness và tenant policy đều đã được kiểm thử.** Chúng cần integration tests với IdP thật và security configuration của tổ chức.

## 13. Khi ghép module này với Kerberos/SPNEGO production

### 13.1. Service principal và keytab

~~~text
Kerberos realm:        EXAMPLE.COM
Public URL:            https://portal.example.com
SPN:                   HTTP/portal.example.com@EXAMPLE.COM
Service keytab:        /run/secrets/portal-http.keytab
KDC/DNS/krb5.conf:     Cấu hình mạng được quản trị
Fallback provider:     OIDC workforce
~~~

Keytab là secret; không đưa vào Git, Docker image công khai, log hoặc UI. Kiểm tra đúng SPN/host, KVNO, encryption types, KDC realm, DNS và đồng bộ giờ. Nếu nhiều nodes, rollout keytab và service principal phải nhất quán.

### 13.2. Mảnh cấu hình entry point và failure handler

~~~java
// MẢNH WIRING, KHÔNG phải Java class độc lập.
// Cần Kerberos extension tương thích Jakarta Servlet của Boot 3.x.
SpnegoEntryPoint entryPoint =
    new SpnegoEntryPoint("/login-choice");

SpnegoAuthenticationProcessingFilter spnegoFilter =
    new SpnegoAuthenticationProcessingFilter();

spnegoFilter.setAuthenticationManager(kerberosManager);
spnegoFilter.setSkipIfAlreadyAuthenticated(true);
spnegoFilter.setFailureHandler((request, response, exception) -> {
    // Không log Authorization: Negotiate header/token.
    response.sendError(401, "Integrated sign-in failed");
});
~~~

`kerberosManager` là bean do hệ thống cấu hình thật với Kerberos service-ticket provider, ticket validator/keytab và local identity mapping. Đoạn này **chỉ minh họa các extension points**, chưa phải runnable project. Không chèn filter một lần vào Spring chain **và** để Servlet container tự đăng ký nó lần hai.

### 13.3. Browser không gửi token: đừng chờ filter báo lỗi

Nếu browser dừng ở challenge, server có thể không nhận token và không có failure handler callback. Cần trang fallback accessible trực tiếp, thử lại Negotiate có giới hạn, không loop. Endpoint OIDC callback phải được permit/protocol filter xử lý, không có Negotiate challenge chặn trước.

### 13.4. Reverse proxy kết thúc Kerberos

Nếu gateway xác minh Kerberos và forward tên user qua header, backend chỉ được tin sau khi:
- Proxy strip mọi inbound `X-Authenticated-User` do client tự đặt;
- Proxy thực sự verify Kerberos, realm, service principal và policy;
- Kênh gateway → app có mTLS/định danh dịch vụ tin cậy;
- Không chấp nhận user header khi gateway thất bại;
- Backend vẫn mapping local identity, role, tenant và assurance;
- Có chống replay/spoofing khi kiến trúc cần bearer assertions.

Header từ Internet **không bao giờ** là “fallback Kerberos” an toàn chỉ vì nó có username.

## 14. Cùng một người: Kerberos principal và OIDC subject

Kerberos thường có principal:

~~~text
alice@EXAMPLE.COM
~~~

OIDC trả identity trong ID Token đã xác minh, ví dụ:

~~~text
iss = https://idp.partner.example/realms/workforce
sub = 7519b1ac-...
email = alice@example.com
~~~

Không tự linking dựa riêng vào email. Email có thể đổi hoặc tái cấp. Thiết kế mapping đã phê duyệt:

~~~text
local_user_id = 104

external identities:
  (KERBEROS, EXAMPLE.COM, alice@EXAMPLE.COM) -> 104
  (OIDC, trusted-issuer, 7519b1ac-...)     -> 104
~~~

Nếu IdP A/B có cùng email, hai `issuer+sub` khác nhau không tự đồng nghĩa cùng local user. Cross-realm Kerberos cũng phải được định danh bằng nguồn đáng tin, không chỉ username phần trước `@`.

### 14.1. Cấm account switch ngầm trong step-up

Một user Kerberos đã đăng nhập rồi được chuyển tới IdP để step-up. Khi callback trở về:
1. Xác minh assertion/token từ IdP đã duyệt.
2. Đối chiếu identity với **chính local user hiện tại** bằng mapping đã được phê duyệt.
3. Nếu subject khác, không gắn MFA evidence vào session của user trước.
4. Nếu đúng, update assurance/freshness có TTL theo policy và rotate session ID khi cần.
5. Lại kiểm tra roles, tenant ownership, disabled status và resource authorization.

Chấp nhận một ID Token hợp lệ **cho user khác** rồi duy trì quyền admin của session trước là lỗi identity mix-up nghiêm trọng.

## 15. MFA step-up cho giao dịch nhạy cảm

Ví dụ:
1. User Kerberos được xác minh, vào `GET /orders` theo policy BASIC.
2. User POST `/orders/471/approve`; policy yêu cầu MFA vừa thực hiện.
3. Spring nhận thấy chưa có validated MFA evidence → không chạy transaction.
4. User được hướng tới IdP với auth request/control theo hợp đồng.
5. IdP thực hiện MFA phù hợp, trả validated ID Token/Assertion có assurance/freshness.
6. SP xác minh cùng subject, `auth_time` và claim context.
7. SP kiểm tra `APP_ORDER_APPROVE` và đúng tenant/resource.
8. Giao dịch chỉ thực hiện nếu **mọi** điều kiện đạt.

`prompt=login`/`max_age` trong OIDC có thể yêu cầu reauthentication theo profile, nhưng **không tự bắt buộc MFA**. Phải yêu cầu đúng authentication context và kiểm tra evidence sau callback.

Không đánh dấu step-up là “vĩnh viễn”. Assurance freshness cần thời hạn, thay đổi khi người dùng logout, session expiry hoặc chuyển tài khoản.

## 16. Tránh protocol downgrade và mở rộng bề mặt credential

### 16.1. SPNEGO có thể không phải Kerberos ở mọi environment

Trong một số cấu hình Windows, Negotiate có thể sử dụng NTLM khi Kerberos thất bại. NTLM có rủi ro relay/credential abuse khác. Tổ chức cần audit/restrict NTLM và kiểm tra protocol thực sự được provider/gateway chấp nhận.

Không gắn `method=KERBEROS` hoặc `phishingResistant=true` chỉ vì thấy HTTP challenge `Negotiate`.

### 16.2. HTTP Basic không thay thế MFA

`WWW-Authenticate: Basic` có thể khiến browser gửi username/password được encode lặp lại theo request. TLS giúp bảo vệ đường truyền nhưng không tự thêm MFA/phishing resistance. Bật Basic fallback tự động có thể khiến user gõ domain password ở nhiều nơi, tăng nguy cơ phishing.

Nếu bắt buộc có password/LDAP flow cho nhóm legacy đã được duyệt, cần LDAPS/TLS, MFA riêng, rate limiting, lockout, password hygiene, identity linking, CSRF, session fixation và controls tương đương theo resource policy.

### 16.3. Không retry “cho tới khi provider nào đó chấp nhận”

Các lỗi `INVALID_NEGOTIATE_TOKEN`, OIDC invalid signature, IdP bị chặn MFA hoặc account disabled không được chuyển thành “thử provider ít bảo vệ hơn cho đến khi có Authentication”. Một lựa chọn thủ công tới IdP hợp lệ **khác** việc tự động bỏ qua authentication check.

## 17. Break-glass trong sự cố toàn diện

Khi KDC, AD và IdP đều unavailable, một số thao tác cứu hệ thống có thể cần **break-glass**, nhưng đó không phải password admin mặc định cho mọi user.

Các điều kiện tối thiểu do chính sách tổ chức xác lập:
1. Danh tính khẩn cấp riêng, không dùng chung với personal account.
2. Credential được lưu vault, truy cập có approval/dual control theo risk policy.
3. Hardware MFA/phishing-resistant method hoặc cơ chế tương đương đã được security phê duyệt.
4. Chỉ có quyền tối thiểu cho tác vụ khôi phục, không toàn quyền business API.
5. TTL/expiration tự động; revoke ngay sau sự cố.
6. Audit realtime và thông báo security, post-incident review.
7. Không kích hoạt qua query `emergency=true` hay một cookie chưa verify.
8. Không sử dụng “KDC outage” như bằng chứng user được phép break-glass.
9. Có lab định kỳ và test kill switch/rotation.
10. Nếu resource yêu cầu mức bảo đảm không đạt được, dừng resource đó thay vì giảm chuẩn.

## 18. Vận hành: Kerberos outage và khả dụng của IdP dự phòng

### 18.1. KDC outage

Kiểm tra:
- DNS SRV KDC/realm, VPN, firewall, network reachability;
- service principal registration/trùng SPN, encryption type, keytab KVNO;
- clock synchronization/NTP;
- trusted Kerberos realm, cross-realm trust;
- browser trusted URIs/enterprise policy;
- server logs đã redacted.

**Điểm quan trọng:** OIDC IdP “dự phòng” có thể vẫn dựa vào cùng Active Directory/KDC, nên **không chắc nó sống độc lập** trong cùng sự cố. Phải test failure domains, không chỉ có hai nút login.

### 18.2. Kế hoạch phục hồi có kiểm soát

1. Xác nhận sự cố, đánh dấu method availability từ observability **không dựa query user**.
2. Hiển thị fallback đã được phê duyệt; không đổi resource policy.
3. Với privileged resource, kiểm tra MFA/phishing resistance/freshness đầy đủ.
4. Theo dõi tỷ lệ fallback, invalid token, identity linking errors.
5. Khắc phục KDC/SPN/keytab/IdP theo root cause; không disable GSS checks.
6. Khi phục hồi, chạy regression tests và rollback feature flags có kiểm soát.
7. Rà soát fallback sessions đang sống, quyền bị revoke và security incident logs.

## 19. Metrics, audit và ranh giới dữ liệu

### 19.1. Metric đề xuất

~~~text
auth_spnego_challenge_total{client_family}
auth_spnego_no_token_total{route_group}
auth_spnego_invalid_ticket_total{reason_class}
auth_fallback_selected_total{provider}
auth_fallback_login_total{provider,result}
auth_assurance_denied_total{resource_group,requirement}
auth_oidc_invalid_response_total{reason_class}
auth_account_link_failure_total{provider}
auth_stepup_result_total{provider,result}
auth_kdc_unavailable_total{realm}
auth_breakglass_total{purpose,result}
auth_redirect_loop_total{client_family}
~~~

Đây là **metric đề xuất**, không phải metric mặc định của Spring. Labels không nên chứa username, UPN, email, raw Kerberos ticket, OIDC token, session ID hoặc user-specific URLs.

### 19.2. Audit record

~~~text
event=authentication_decision
attempt_id=internal-random-id
source=KERBEROS|OIDC|SAML|BREAK_GLASS
trusted_realm_or_issuer=approved-reference
identity_link=PASS|FAIL
account_state=ACTIVE|DISABLED
resource_requirement=WORKFORCE_MFA
assurance_evidence=VERIFIED|INSUFFICIENT|STALE
local_authorization=ALLOW|DENY
result=ALLOW|CHALLENGE|DENY
reason_class=NO_TOKEN|KDC_OUTAGE|MFA_MISSING|...
~~~

Không log `Authorization: Negotiate`, ID Token/access token, keytab, passwords hoặc MFA secrets. Nếu cần điều tra user, dùng ID nội bộ có hạn chế truy cập và retention phù hợp.

### 19.3. Alert

| Dấu hiệu | Hướng xử lý |
| --- | --- |
| Tỷ lệ fallback tăng đột ngột | Điều tra KDC/SPN/role changes và downgrade attack. |
| Invalid Negotiate ticket tăng | Phân tích token spoofing/replay/clock drift; rate limit theo policy. |
| ACR mismatch trên admin tăng | Kiểm tra IdP MFA configuration và assurance mapping; fail closed. |
| Identity linking bất thường | Ngừng auto-link và kiểm tra account takeover. |
| Privileged access sau fallback không MFA | Incident nghiêm trọng; revoke sessions và sửa policy. |
| OIDC callback nhận 401 Negotiate/302 loop | Sửa SecurityFilterChain matchers/filter order. |
| Break-glass ngoài sự cố đã được duyệt | Security alert, hậu kiểm và thu hồi. |

## 20. Bộ kiểm thử tích hợp

| ID | Tình huống | Kết quả |
| --- | --- | --- |
| F01 | Domain-joined browser, ticket Kerberos hợp lệ, account ACTIVE. | Login thành công cho BASIC resource. |
| F02 | Browser không gửi `Authorization: Negotiate`. | Có lựa chọn fallback; không có Authentication giả. |
| F03 | Browser tự bỏ cuộc sau 401. | Không loop; user có thể vào login-choice. |
| F04 | Negotiate token giả. | Reject; không cấp role. |
| F05 | Negotiate thực tế chọn NTLM trái policy. | Reject/downgrade blocked theo configuration. |
| F06 | SPN không khớp host. | Kerberos validation fail; không bypass. |
| F07 | Keytab KVNO cũ trên một node. | Báo lỗi ops; fallback vẫn theo policy. |
| F08 | KDC offline, OIDC hoạt động. | Login OIDC được phép nếu evidence đạt. |
| F09 | OIDC cũng phụ thuộc AD/KDC outage. | Không có bypass, fail closed. |
| F10 | OIDC issuer khác allowlist. | Reject assertion. |
| F11 | ID Token signature/exp/aud sai. | Reject. |
| F12 | OIDC state/nonce sai. | Reject. |
| F13 | Authorization Code bị replay. | Protocol reject. |
| F14 | OIDC redirect URL sai host/HTTPS. | Reject/sửa trusted settings. |
| F15 | IdP chỉ password, resource BASIC. | Chỉ chấp nhận nếu approved policy cho phép. |
| F16 | IdP chỉ password, resource MFA. | Deny/step-up. |
| F17 | MFA bằng OTP nhưng resource đòi phishing resistance. | Deny/step-up. |
| F18 | ACR chưa được mapping hoặc thiếu. | Deny privileged resource. |
| F19 | ACR đúng, `auth_time` quá cũ. | Step-up fresh auth. |
| F20 | ACR đúng nhưng local admin role thiếu. | Deny. |
| F21 | OIDC identity valid nhưng local account disabled. | Deny. |
| F22 | Same email ở hai IdP, issuer/sub khác. | Không auto-link. |
| F23 | Kerberos principal và OIDC subject đã linked hợp lệ. | Dùng cùng local user ID. |
| F24 | Step-up OIDC trả subject khác user Kerberos. | Reject/account-switch handling; không giữ quyền cũ. |
| F25 | Session ID không rotate khi auth thành công. | Test phát hiện fixation risk. |
| F26 | API machine nhận 302 HTML login thay vì 401. | Test fail; tách API chain. |
| F27 | Fallback page bị Negotiate challenge chặn. | Test fail; permitAll/route fix. |
| F28 | OIDC callback bị SPNEGO filter chiếm. | Test fail; matcher/order fix. |
| F29 | Browser gửi `returnTo=https://evil.example`. | Không open redirect. |
| F30 | Browser gửi `X-Authenticated-User: admin`. | Header bị strip/không tin. |
| F31 | Browser gửi issuer/realm tùy ý. | Không thay approved trust config. |
| F32 | Account bị revoke khi Kerberos session còn. | Authorization/session revocation áp đúng. |
| F33 | Fallback session có cookie insecure. | QA fail, enforce secure attributes. |
| F34 | Fallback login dùng Basic vô điều kiện. | QA fail theo policy, không bật tự động. |
| F35 | KDC outage và break-glass chưa phê duyệt. | Deny. |
| F36 | Break-glass đã duyệt hết TTL. | Revoke scope/privilege, audit. |
| F37 | Brute-force/password attempts trên fallback. | Rate limit và lockout. |
| F38 | User thuộc tenant A dùng IdP B. | Không cross-tenant access. |
| F39 | Proxy forward spoofed identity header. | Reject; mTLS/attestation cần thiết. |
| F40 | Kerberos fail do clock skew. | Sửa NTP; không nới validation vô hạn. |
| F41 | MFA step-up hoàn tất nhưng user khác. | Reject identity mismatch. |
| F42 | Admin thiếu device compliance theo policy. | Deny dù login hợp lệ. |
| F43 | OIDC client secret hoặc keytab lọt vào log. | QA fail/rotate/incident. |
| F44 | Kerberos được sửa, user thử lại Negotiate. | Khôi phục flow bình thường, không hạ policy. |

### 20.1. Lab A — SPNEGO và fallback

1. Chuẩn bị KDC/AD test, đúng SPN, keytab và browser domain-joined.
2. Xác nhận 401 Negotiate → Authorization Negotiate được accept hợp lệ.
3. Dùng browser không domain: không có token; hiển thị trang fallback.
4. Thử malformed token trong test environment và kiểm tra không có session giả.
5. Tạm tắt KDC test, xác nhận OIDC fallback nhưng vẫn dùng resource policy.

### 20.2. Lab B — assurance và account linking

1. IdP OIDC test có MFA/passkey và ACR theo contract.
2. Mở dashboard với evidence BASIC; mở admin với evidence thiếu MFA và quan sát deny.
3. Hoàn tất step-up cùng identity, kiểm tra auth_time/freshness và local role.
4. Thử subject khác, ACR không biết, user disabled, tenant sai.
5. Giữ nguyên kiểm tra role/tenant khi đổi login method.

### 20.3. Lab C — outage và break-glass

1. Mô phỏng sai keytab, clock skew, DNS/KDC outage, IdP outage.
2. Kiểm tra logs/metrics không có raw credentials.
3. Thử kill switch cho phương thức fallback, rotation keytab/secrets.
4. Mô phỏng phê duyệt break-glass có thời hạn và audit.
5. Đảm bảo không có lối tắt chỉ-password cho resource high-risk.

## 21. Câu hỏi tự đánh giá

**1. Có thể tự bật HTTP Basic khi Kerberos không gửi ticket?**  
Không. Một authentication method khác chỉ được dùng nếu đã được duyệt và đáp ứng policy.

**2. Vì sao filter failure handler không giải quyết mọi browser không hỗ trợ?**  
Browser có thể không gửi token; không có authentication exception phía server để gọi handler.

**3. OIDC login success có đồng nghĩa MFA không?**  
Không. IdP phải thực hiện MFA và cung cấp evidence được SP xác minh theo contract.

**4. ACR là một thang assurance toàn cầu cố định?**  
Không. Giá trị ACR do IdP/profile định nghĩa và cần mapping exact-value.

**5. Kerberos ticket valid có luôn là phishing-resistant MFA?**  
Không. Phải xét authenticator ceremony/device/evidence, không suy từ protocol.

**6. OIDC ID Token có email trùng Kerberos username, có tự link không?**  
Không. Dùng trusted issuer+sub và realm/principal/immutable identity mapping đã duyệt.

**7. Local account disabled nhưng IdP OIDC success?**  
Vẫn DENY.

**8. Một resource cần phishing resistance nhưng IdP chỉ có SMS OTP?**  
Deny/step-up với authenticator đáp ứng policy.

**9. Người dùng Kerberos A step-up OIDC bằng account B thì sao?**  
Không gắn evidence của B vào A hoặc giữ quyền của A.

**10. KDC outage có là giấy phép break-glass?**  
Không. Cần phê duyệt/credential riêng/TTL/audit.

**11. Khi fallback IdP không hoạt động, có thể tạm cấp ROLE_USER?**  
Không; fail closed cho authentication mới.

**12. Basic resource và admin resource có thể có yêu cầu khác nhau?**  
Có, miễn chính sách áp đúng ở resource/action và không được bypass.

**13. Tại sao API không nên trả login HTML 302 cho machine client?**  
Vì machine protocol cần 401/403 hoặc OAuth2/mTLS phù hợp, tránh vòng lặp và lỗi xử lý.

**14. Nếu gateway forward `X-Authenticated-User`, khi nào tin được?**  
Chỉ qua authenticated gateway và trusted protected channel, header client được strip.

**15. SSO bằng Kerberos không cần nhập password có chứng minh user vừa MFA không?**  
Không; đó là đặc tính UX của SSO, cần evidence riêng cho MFA/freshness.

## 22. Checklist production

- [ ] Resource policy định nghĩa BASIC, MFA, PHISHING_RESISTANT_FRESH chính xác.
- [ ] Không gán AAL/MFA chỉ từ “Kerberos” hoặc “OIDC”.
- [ ] Phân loại no-token, KDC outage, config error, invalid token, disabled account riêng.
- [ ] SPNEGO token verify bằng provider/GSS-API/realm/keytab thật, không provider giả.
- [ ] NTLM/Basic downgrade không bật tự động nếu chưa được security duyệt.
- [ ] Fallback OIDC/SAML chỉ dùng IdP/issuer/redirect URI từ trusted config.
- [ ] OIDC Authorization Code, PKCE, state/nonce, token validation, HTTPS đúng framework/version.
- [ ] ACR/AMR/auth_time mapping có hợp đồng, thực hiện step-up cho resource nhạy cảm.
- [ ] Account linking Kerberos realm/principal ↔ OIDC issuer/sub được duyệt.
- [ ] Disabled user, local role, tenant và resource ownership kiểm tra ở mọi method.
- [ ] Callback OIDC và trang fallback không bị Negotiate challenge/redirect loop chặn.
- [ ] Browser CSRF/session fixation/cookie/reauth policies giữ nguyên khi đổi method.
- [ ] API machine client có security chain/response riêng.
- [ ] Reverse proxy strip untrusted headers và kiểm soát forwarded host/origin.
- [ ] Keytab/secret theo vault, KVNO/rotation và NTP kiểm soát.
- [ ] Đã test IdP và KDC có failure domain độc lập thật hay không.
- [ ] Break-glass có approval, MFA, least privilege, TTL, alerts và hậu kiểm.
- [ ] Log không có raw Kerberos ticket, password, tokens, keytab; metrics ít PII.
- [ ] Có kill switch và rollback plan mà không nới policy.
- [ ] Test F01–F44 hoặc coverage tương đương được chạy trong staging.
- [ ] Kiểm tra version tương thích Spring Security Kerberos extension/Jakarta Servlet trước go-live.

## Ghi nhớ

> **Kerberos/SPNEGO bị lỗi không phải lý do giảm chuẩn xác thực.** Chỉ cho phép fallback đến **phương thức đã được duyệt và thật sự được xác minh**, với MFA/phishing resistance/freshness đáp ứng yêu cầu của tài nguyên; tiếp tục kiểm tra local user, quyền và tenant. Nếu không có phương thức phù hợp, **fail closed** và cung cấp hướng dẫn hỗ trợ, thay vì tự động hạ cấp sang NTLM, Basic, password-only hoặc tin header tự khai.

### Tài liệu tham khảo chính thức

- [Spring Security Kerberos — SpnegoEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): challenge Negotiate và fallback URL.
- [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): filter/AuthenticationManager/failure handler và browser không gửi token.
- [Spring Security Kerberos Extension source](https://github.com/spring-projects/spring-security-kerberos): modules, samples, compatibility.
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Authorization Code, OIDC client registration và callback.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): resource authorization, AuthorizationManager.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext, session fixation, logout.
- [NIST SP 800-63B-4 (2025)](https://pages.nist.gov/800-63-4/sp800-63b.html): Authenticator Assurance Levels và MFA/phishing resistance.
- [Microsoft — Integrated Windows Authentication](https://learn.microsoft.com/en-us/aspnet/web-api/overview/security/integrated-windows-authentication): Kerberos/NTLM và intranet limitations.
- [Microsoft — Restrict NTLM authentication](https://learn.microsoft.com/windows/security/threat-protection/security-policy-settings/network-security-restrict-ntlm-ntlm-authentication-in-this-domain): chính sách audit/restrict NTLM.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, acr, amr, auth_time.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): MFA, authentication controls và brute-force.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, cookie và revocation.
