# Xử lý người dùng hợp lệ tại IdP nhưng bị khóa hoặc chưa được cấp quyền tại ứng dụng

Trong **Spring Security federation**, một người dùng có thể đăng nhập thành công tại **Identity Provider (IdP)**, hoàn thành MFA và nhận SAML 2.0 assertion có chữ ký hợp lệ, nhưng vẫn **không được Service Provider (SP) cho phép truy cập ứng dụng**. Lý do: tổ chức có thể đã khóa tài khoản nội bộ, chưa provisioning người dùng, đang chờ phê duyệt, hết license, không thuộc tenant cần truy cập hoặc chưa cấp quyền cho tính năng/tài nguyên.

Ví dụ: nhân viên vẫn có tài khoản trong IdP công ty nhưng đã bị khóa ở ứng dụng tài chính do kiểm tra bảo mật. Nếu SP tự cấp session và quyền `ROLE_USER` ngay sau xác minh SAML mà không xét trạng thái cục bộ, kết quả là **vượt qua quyết định khóa của ứng dụng**, dù IdP hoàn toàn hợp lệ.

**Nguyên tắc:** `SAML authentication` trả lời “chủ thể là ai theo IdP?”, **application admission** trả lời “có được dùng ứng dụng này không?”, còn **authorization** trả lời “được thực hiện thao tác nào trên tài nguyên nào?”. Cả ba điều kiện phải được thực thi độc lập và kết hợp theo kiểu **deny by default**.

## 1. Ba lớp kiểm tra khác nhau

| Lớp | Điều cần biết | Cơ chế/điểm quyết định | Kết quả |
| --- | --- | --- | --- |
| **Xác thực liên kết tại IdP** | Ai đã xác thực? Response/assertion có đáng tin và còn hạn? | Chữ ký, issuer, audience, destination/recipient, conditions, subject confirmation, `InResponseTo`, replay. | Tạo **danh tính liên kết đã được xác minh**. |
| **Admission của ứng dụng** | Danh tính này đã có account cục bộ chưa? Account có bị LOCKED/DISABLED/PENDING không? Có quyền vào sản phẩm này không? | Tra local identity binding, trạng thái tài khoản, license, phê duyệt onboarding, tenant và chính sách vòng đời. | **Cho phép hoặc từ chối thiết lập session ứng dụng**. |
| **Authorization tài nguyên** | Tài khoản được phép xem/sửa báo cáo, đơn hàng hay dữ liệu tenant này không? | RBAC, ABAC, permission, ownership, tenant policy, trạng thái tài khoản cập nhật. | **Cho phép hoặc 403** đối với một thao tác cụ thể. |

Cùng một SAML assertion hợp lệ có thể dẫn tới các quyết định khác nhau:

- **LOCKED/DISABLED:** không tạo phiên mới cho ứng dụng; không coi đăng nhập IdP là mở khóa.
- **PENDING_APPROVAL/NO_LOCAL_ACCOUNT:** chưa cho dùng chức năng nghiệp vụ; chỉ JIT provisioning khi có chính sách và điều kiện rõ.
- **ACTIVE nhưng thiếu `reports:read`:** có thể cho vào trang chủ nhưng từ chối API báo cáo.
- **ACTIVE với quyền báo cáo tenant A:** không được đọc tài nguyên tenant B chỉ vì URL chứa `tenantId=B`.

Đặc biệt, **quyền do ứng dụng quyết định** phải có thể thu hồi độc lập với phiên SSO của IdP. SAML hợp lệ không biến người dùng thành quản trị viên.

## 2. Đường đi của SAML login và điểm kiểm tra account

~~~text
Browser                 SP / Spring Security                     IdP
   |                            |                                  |
   | GET /reports/42            |                                  |
   |--------------------------->|                                  |
   |                            | AuthnRequest                     |
   |<---------------------------|                                  |
   |------------------------------------------------------------->|
   |                            |                           SSO/MFA |
   |<-------------------------------------------------------------|
   | POST SAMLResponse đến ACS  |                                  |
   |--------------------------->|                                  |
   |                            v                                  |
   |               Saml2WebSsoAuthenticationFilter                |
   |                            |                                  |
   |               AuthenticationManager / OpenSAML                |
   |                 - issuer, chữ ký, thời hạn                    |
   |                 - audience, recipient, InResponseTo          |
   |                 - subject confirmation, replay               |
   |                            |                                  |
   |                    VALIDATED IDENTITY                         |
   |                            |                                  |
   |                  Lookup local identity binding                |
   |                            |                                  |
   |                 +----------+-----------+                      |
   |                 |                      |                      |
   |          LOCKED/DISABLED/           ACTIVE +                  |
   |          PENDING/NO ACCOUNT        admitted                   |
   |                 |                      |                      |
   |           từ chối login          Authentication +             |
   |           không tạo session      SecurityContext              |
   |                                        |                      |
   |                              Authorization /reports/42       |
   |                                   ALLOW hoặc 403              |
~~~

`Saml2WebSsoAuthenticationFilter` nhận phản hồi tại **ACS**, converter định tuyến đến cấu hình `RelyingPartyRegistration`, authentication manager chuyển cho OpenSAML provider để xác minh. **Application admission** nên được nối vào quá trình xử lý **sau khi SAML đã được xác minh, nhưng trước khi Authentication/session được công bố là thành công**. Resource authorization vẫn cần thiết ngay cả khi admission cho phép.

**Tránh cách làm sai:** chỉ kiểm tra tài khoản ở trang chủ sau khi Spring Security đã lưu session, rồi chuyển tài khoản bị khóa sang trang lỗi. Nếu API hay controller khác không có cùng kiểm tra, cookie phiên có thể vẫn gọi được dữ liệu. Cũng không nên thay SAML validator bằng một truy vấn `user.status == ACTIVE` mà bỏ kiểm tra chữ ký và issuer.

## 3. Ánh xạ đúng danh tính liên kết vào tài khoản nội bộ

### 3.1. Không dựa duy nhất vào email hoặc tên hiển thị

IdP có thể phát hành `NameID`, `email`, `groups` và các thuộc tính khác. Không phải giá trị nào cũng ổn định và phù hợp làm khóa tài khoản. Email có thể đổi, được tái sử dụng hoặc trùng giữa các môi trường; SAML `NameID` còn có định dạng transient không dùng lại qua nhiều lần login.

Một bảng liên kết danh tính có thể lưu:

~~~text
federated_identity
  issuer_id        = "urn:example:idp:corporate"
  stable_subject   = "employee-9732a..."
  tenant_scope     = "tenant-acme"
  local_user_id    = "user-42"
  binding_status   = "VERIFIED"

local_account
  local_user_id    = "user-42"
  status           = "LOCKED"
  reason_code      = "SECURITY_REVIEW"
  entitlements     = []
~~~

Khóa liên kết nên gồm **trusted IdP/issuer + stable subject**, cùng tenant/organization scope khi phù hợp. Stable subject có thể là persistent NameID hoặc một attribute bất biến đã được IdP cam kết và phát hành qua assertion đã xác minh; chọn dựa trên hợp đồng federation thật. **Không lấy một trường issuer/subject tự khai từ HTTP request để tra local account rồi cho đăng nhập.**

Một tài khoản từng bị khóa phải vẫn được tìm thấy qua binding này. Nếu query chỉ tìm `status=ACTIVE`, hệ thống có thể hiểu sai rằng “chưa có tài khoản” rồi **tự JIT tạo tài khoản mới**, vượt qua trạng thái khóa.

### 3.2. Multi-IdP và migration danh tính

Trong hệ thống có nhiều IdP, cùng một email có thể được phát từ các issuer khác nhau. Không tự hợp nhất `alice@example.org` tại IdP A với `alice@example.org` tại IdP B. Với migration thay đổi issuer/NameID, phải có kế hoạch **re-link có bằng chứng**, phê duyệt và audit. Nếu không tìm được binding, xử lý theo chính sách `NO_LOCAL_ACCOUNT`, không cấp quyền từ bản ghi “gần giống” theo email.

| Dữ liệu đã được xác minh từ IdP | Có thể dùng làm | Không nên dùng làm |
| --- | --- | --- |
| `Issuer` và registration | Phân định nguồn danh tính tin cậy. | Tự thêm một issuer mới không được phê duyệt. |
| Persistent NameID / immutable subject | Khóa liên kết nội bộ theo chính sách. | Tự coi mọi loại NameID là bất biến. |
| Email | Thông tin liên hệ và onboarding có kiểm soát. | Bằng chứng duy nhất để nối/khôi phục quyền cũ. |
| Group attributes | Một đầu vào cho mapping quyền đã phê duyệt. | Tự động cấp mọi role có cùng tên. |
| `RelayState` | Correlation/login navigation. | Account ID, tenant ID hoặc quyền quản trị. |

## 4. Chính sách account state: local deny có ưu tiên cao

Đề xuất tập trạng thái nội bộ:

| Trạng thái | IdP có thể hợp lệ? | Xử lý tại ứng dụng |
| --- | --- | --- |
| `ACTIVE` | Có | Cho phép admission nếu tenant/license/điều kiện khác đều đáp ứng. |
| `LOCKED` | Có | **Không cho login mới**; không gỡ khóa theo SAML. Thu hồi session/token đã cấp theo SLA. |
| `DISABLED` / `DEPROVISIONED` | Có | Từ chối; không tự tái tạo account bằng JIT. |
| `PENDING_APPROVAL` | Có | Chờ phê duyệt; có thể hiện trang trạng thái giới hạn, không cấp quyền sản phẩm. |
| `NO_LOCAL_ACCOUNT` | Có | Deny mặc định hoặc JIT được quản trị chặt, không có quyền mặc định vượt chính sách. |
| `ACTIVE` nhưng chưa có role | Có | Có thể cho vào shell tối thiểu hoặc chặn admission tùy chính sách; mọi tính năng cần permission riêng. |
| `ACTIVE` nhưng sai tenant | Có | Từ chối tài nguyên tenant khác, không dùng tenant ID từ URL làm bằng chứng membership. |
| `UNKNOWN` do DB/status store lỗi | Có | **Fail closed** đối với quyết định quyền bắt buộc; không giả định account vẫn active. |

**Thứ tự kiểm tra an toàn:** tìm identity binding đúng → xét `DISABLED/LOCKED` → xét trạng thái approval/admission → xét tenant membership/license → xét role/permission/resource. Nếu có nhiều điều kiện, **deny thắng allow**. Ví dụ SAML assertion chứa group admin nhưng local account bị khóa vẫn phải từ chối.

### 4.1. Quyền vào ứng dụng khác với quyền vào một feature

Có hai lựa chọn hợp lệ, phải nhất quán với sản phẩm:

1. **Không có entitlement sử dụng ứng dụng → từ chối admission.** Phù hợp ứng dụng có license hoặc phê duyệt toàn sản phẩm.
2. **Cho phép truy cập trang chung/onboarding nhưng hạn chế tính năng → admission giới hạn, từ chối resource bằng authorization.** Phải đảm bảo trang chung không gọi API nhạy cảm và không được cấp quyền nghiệp vụ do `ROLE_USER` mặc định.

Một người chưa có quyền xem báo cáo **không nhất thiết là tài khoản bị khóa**, nên hướng dẫn/khả năng hỗ trợ khác nhau. Tuy nhiên, nếu yêu cầu kinh doanh là “chưa được phê duyệt thì không được vào bất kỳ trang nào”, admission gate phải chặn ngay tại login.

## 5. JIT provisioning có điều kiện, không tự mở quyền

**JIT (Just-in-Time) provisioning** có thể tạo local account sau lần SAML login đầu tiên. Không nên coi `SAMLResponse` hợp lệ là yêu cầu cấp quyền vô điều kiện.

Cần tối thiểu:

1. **Issuer được allowlist** và subject ổn định, đã xác minh.
2. **Eligibility rõ ràng:** tenant, license, tổ chức, group được duyệt hoặc lời mời có xác thực; không chỉ kiểm tra email domain.
3. **Unique constraint** cho `(issuer, stableSubject, tenantScope)`; thao tác tạo account phải chịu race từ nhiều callback/nút.
4. **Kiểm tra lịch sử khóa/deprovision:** query binding bao gồm cả LOCKED/DISABLED/tombstone. Không tạo account mới để đi vòng qua account cũ đã khóa.
5. **Trạng thái ban đầu an toàn:** `PENDING_APPROVAL` hoặc `ACTIVE` với least privilege, chỉ khi chính sách cho phép.
6. **Audit:** lưu quyết định tại thời điểm tạo, policy version, nguồn danh tính, tenant và approver nếu có.
7. **Xử lý lỗi:** khi hết quota/không xác định tenant hoặc datastore lỗi, từ chối/để pending; không suy ra quyền admin.
8. **Deprovisioning:** kế hoạch disable/revoke khi HR/IAM thu hồi quyền; không chỉ trông chờ lần login SAML tiếp theo.

Nếu quản trị muốn tạo tài khoản trước qua **SCIM**, SAML và SCIM có trách nhiệm khác nhau: **SCIM** đồng bộ vòng đời/provisioning, còn **SAML** chứng minh danh tính tại thời điểm login. Trong cửa sổ đồng bộ chậm, local deny vẫn phải được tôn trọng.

## 6. Java 17 chạy độc lập: xác minh chính sách local

Ví dụ Java 17 mô phỏng một danh tính đã **được SAML xác minh trước đó**, tra local account và kiểm tra trạng thái/tenant/quyền. Đây **không phải implementation của OpenSAML**, không parse XML và không cấp `SecurityContext`; mục đích là minh họa việc SAML identity hợp lệ nhưng quyền ứng dụng bị từ chối.

Tệp `FederatedAccountPolicyDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class FederatedAccountPolicyDemo {

    record Identity(String issuer, String subject) {}
    enum Status { ACTIVE, LOCKED, DISABLED, PENDING_APPROVAL }
    enum Decision {
        ALLOW, NOT_PROVISIONED, ACCOUNT_LOCKED,
        ACCOUNT_DISABLED, PENDING_APPROVAL,
        TENANT_DENIED, PERMISSION_DENIED
    }
    record Account(Status status, String tenant,
                   Set<String> permissions) {}

    static Decision decide(Identity verified, String tenant,
                           String permission,
                           Map<Identity, Account> accounts) {
        Account account = accounts.get(verified);
        if (account == null) {
            return Decision.NOT_PROVISIONED;
        }
        if (account.status() == Status.LOCKED) {
            return Decision.ACCOUNT_LOCKED;
        }
        if (account.status() == Status.DISABLED) {
            return Decision.ACCOUNT_DISABLED;
        }
        if (account.status() == Status.PENDING_APPROVAL) {
            return Decision.PENDING_APPROVAL;
        }
        if (!account.tenant().equals(tenant)) {
            return Decision.TENANT_DENIED;
        }
        if (!account.permissions().contains(permission)) {
            return Decision.PERMISSION_DENIED;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        String issuer = "urn:example:idp:corporate";
        Identity alice = new Identity(issuer, "subject-alice");
        Identity bob = new Identity(issuer, "subject-bob");
        Identity carol = new Identity(issuer, "subject-carol");
        Identity dave = new Identity(issuer, "subject-dave");

        Map<Identity, Account> accounts = Map.of(
            alice, new Account(Status.ACTIVE,
                               "tenant-A", Set.of("reports:read")),
            bob, new Account(Status.LOCKED,
                             "tenant-A", Set.of("reports:read")),
            carol, new Account(Status.PENDING_APPROVAL,
                               "tenant-A", Set.of())
        );

        System.out.println(decide(
            alice, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            bob, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            carol, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            dave, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            alice, "tenant-A", "reports:write", accounts));
        System.out.println(decide(
            alice, "tenant-B", "reports:read", accounts));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FederatedAccountPolicyDemo.java
java FederatedAccountPolicyDemo
~~~

Kết quả chính xác:

~~~text
ALLOW
ACCOUNT_LOCKED
PENDING_APPROVAL
NOT_PROVISIONED
PERMISSION_DENIED
TENANT_DENIED
~~~

Hai dòng cuối cho thấy **ngay cả account ACTIVE cũng không thể truy cập mọi tài nguyên**. Demo dùng `Map` tĩnh, chỉ hỗ trợ một tenant trên một account, không bao gồm trạng thái license, session revocation, DB hoặc SAML validation; production cần lưu trữ và policy chuyên biệt. **Identity được cung cấp cho `decide` phải đến từ assertion đã được xác minh**, tuyệt đối không lấy trực tiếp từ HTTP header/URL chưa tin.

## 7. Spring Security: admission gate phải được nối vào SAML flow

### 7.1. Vì sao `UserDetailsService` không tự giải quyết bài toán?

Với form login, `DaoAuthenticationProvider` dùng `UserDetailsService`/account-status checker và có thể xét `isEnabled()`, `isAccountNonLocked()` trong `UserDetails`. Nhưng luồng **SAML** dùng **OpenSAML authentication provider**, không mặc nhiên qua `DaoAuthenticationProvider`. Chỉ thêm một trường `enabled=false` trong DB hoặc đăng ký bean `UserDetailsService` **không bảo đảm** SAML user bị chặn.

Spring Security có `DisabledException`, `LockedException` trong các tình huống account status không đạt. Khi tùy biến SAML provider/converter hoặc admission component, dùng tín hiệu `AuthenticationException` phù hợp để đảm bảo request đi qua **authentication failure path**, không tạo một đối tượng `Authentication` thành công rồi để giao diện tự xử lý.

### 7.2. Mẫu kiến trúc admission gate

~~~text
verifyWithOpenSaml(samlResponse, trustedRegistration, pendingRequest)
    -> verified issuer + persistent subject + claims

binding = localIdentityRepository.findIncludingDisabled(issuer, subject)

if no binding:
    if explicit JIT policy passes:
        binding = createAccountWithUniqueConstraint(leastPrivilege)
    else:
        throw AuthenticationException(NOT_PROVISIONED)

account = accountRepository.loadCurrent(binding.localUserId)

if account.status == LOCKED:
    throw LockedException(ACCOUNT_LOCKED)
if account.status == DISABLED:
    throw DisabledException(ACCOUNT_DISABLED)
if account.status == PENDING_APPROVAL:
    throw AuthenticationException(APPROVAL_REQUIRED)
if account.status != ACTIVE:
    throw AuthenticationException(ADMISSION_DENIED)
if not account.hasApplicationEntitlement:
    throw AuthenticationException(APP_NOT_ASSIGNED)

authorities = mapOnlyApprovedApplicationEntitlements(account)
return authenticatedResultWithLocalAccountId(authorities)
~~~

Đây là **pseudocode**, không phải API có sẵn hoặc ví dụ có thể copy và chạy. Cần thực hiện admission check **sau** SAML validation nhưng **trước** khi authentication thành công được công bố. Tránh tạo session trong một custom controller trước khi status check hoàn thành.

Tài liệu Spring Security hỗ trợ tùy biến `OpenSamlXAuthenticationProvider#setResponseAuthenticationConverter` để chuyển response đã xử lý thành `Authentication`. Có thể ủy quyền cho converter mặc định và bổ sung account lookup/status/authority mapping, hoặc dùng extension point được tài liệu **phiên bản cụ thể** hỗ trợ. `OpenSaml4AuthenticationProvider` ở một số bản 6.x và `OpenSaml5AuthenticationProvider` ở các bản mới có API khác nhau; phải xác nhận dependency đang dùng. Không vô hiệu hóa default signature, issuer, audience, recipient, conditions, `InResponseTo` hoặc replay validators để dễ tích hợp kiểm tra local account.

### 7.3. Cấu hình `SecurityFilterChain` và quyền tối thiểu

Tệp `src/main/java/example/security/FederationSecurityConfig.java` trong dự án Spring Boot đã có SAML registration hợp lệ:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/help", "/access-pending", "/error")
                    .permitAll()
                .requestMatchers("/admin/**")
                    .hasAuthority("app:admin")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Cấu hình này chỉ **bật SAML login và rule URL/method security**. Nó **chưa triển khai admission gate**, chưa có IdP metadata, chưa map approved entitlements và không thể `javac` độc lập chỉ với JDK. Nếu đem nguyên ví dụ vào production mà bỏ qua admission component, bài toán tài khoản bị khóa vẫn chưa được giải quyết.

`@EnableMethodSecurity` cho phép dùng `@PreAuthorize` ở service. Ví dụ:

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readSummary() {
        return "Report summary";
    }
}
~~~

Đoạn trên minh họa một **service trong Spring project**, không chứa controller hay kiểm tra ownership của từng report ID. Hệ thống multi-tenant còn phải thực thi logic như:

~~~text
authentication is present?
localAccount is currently ACTIVE?
approvedPermissions contains "reports:read"?
localAccount belongs to request.tenantId?
requestedReport.tenantId == request.tenantId?
requestedReport is visible to this principal?
=> all true, otherwise deny
~~~

Không chỉ dựa vào nút được ẩn ở UI, query parameter `tenantId`, hay một `ROLE_USER` mặc định. Authority mapping phải lấy từ entitlement ứng dụng đã duyệt; group SAML chỉ được dùng nếu có hợp đồng mapping tin cậy và **không vượt qua local lock**.

### 7.4. Điểm mở rộng và điều không nên làm

| Nhu cầu | Điểm mở rộng phù hợp | Điều phải giữ |
| --- | --- | --- |
| Tra local user sau SAML validation | Response authentication conversion/provider extension, hoặc admission component được tích hợp vào SAML authentication manager. | Giữ toàn bộ SAML validators mặc định và ngăn tạo session khi account bị khóa. |
| Ánh xạ IdP subject → local user | Identity-binding repository có unique constraint. | Issuer/subject ổn định, chặn merge bằng email chưa bảo đảm. |
| Ánh xạ quyền | Approved entitlement service và authority mapper. | Deny precedence, chỉ map group đã allowlist và kiểm tra tenant. |
| Kiểm tra quyền URL | `authorizeHttpRequests`. | Mặc định authenticated chưa đủ cho tài nguyên nhạy cảm. |
| Kiểm tra quyền phương thức/tài nguyên | `@EnableMethodSecurity`, `@PreAuthorize`, business policy. | Tenant ownership/resource authorization. |
| Lỗi account/redirect | Authentication failure handler, access denied handler. | Không tạo login loop và không lộ SAMLResponse. |
| Khóa account đang có session | Spring Session/session registry, policy status/version, revocation service. | Thu hồi trên mọi node và API tokens theo SLA. |

## 8. Khi khóa tài khoản sau khi đã đăng nhập

Đây là một lỗ hổng lifecycle phổ biến: user login SAML lúc 09:00, tạo phiên SP sống đến 17:00; lúc 09:10 admin khóa local account, nhưng SP chỉ kiểm tra status tại callback 09:00. Nếu `SecurityContext` trong session lưu `Authentication` với quyền cũ, user vẫn có thể gọi API cho đến khi session hết hạn.

Các cách giảm rủi ro:

- **Session revocation:** tra tất cả phiên của `localUserId` và invalidate bằng kho phiên chung (ví dụ Spring Session) hoặc cơ chế thu hồi riêng. Có kế hoạch multi-node/multi-region.
- **Account security version:** lưu `securityVersion` hoặc `revokedAfter` của account; mỗi request quan trọng so sánh với session/token hiện tại.
- **Re-check ở business boundary:** đọc trạng thái account và entitlement mới trước hành động nhạy cảm; cache ngắn và có invalidation nếu SLA thu hồi quyền chặt.
- **JWT/stateless APIs:** JWT đã phát không tự bị thu hồi chỉ vì DB đổi `LOCKED`. Cần TTL ngắn, introspection/revocation hoặc policy check theo account hiện hành ở Resource Server.
- **Event-driven offboarding:** khi HR/SCIM/IAM disable account, phát sự kiện thu hồi session/token/role; có retry, audit và xử lý event trễ.
- **Cross-SP behavior:** khóa tại một SP không đồng nghĩa IdP hoặc mọi SP khác tự logout. Nếu là khóa bảo mật tổ chức, phải điều phối với IAM/IdP và các SP liên quan.

**Không hứa “khóa tức thì”** nếu status/entitlement cache thực tế stale 15 phút hoặc revocation chỉ chạy ở lần login tiếp theo. Kiểm thử SLA trên tất cả replicas, sau failover và trong trường hợp datastore lỗi.

## 9. Phân biệt kết quả HTTP và trải nghiệm người dùng

| Trạng thái | Xử lý thường phù hợp | Ghi chú |
| --- | --- | --- |
| Chưa xác thực gọi API | **401 Unauthorized** hoặc redirect tới IdP với ứng dụng web. | Do `AuthenticationEntryPoint` quyết định. |
| SAML response không hợp lệ | Authentication failure. | Không giả mạo thông báo “tài khoản bị khóa” để che lỗi signature. |
| SAML hợp lệ nhưng local `LOCKED/DISABLED` | Authentication failure, không tạo phiên SP. | Endpoint ACS có thể redirect tới trang lỗi thay vì HTTP 401 trực tiếp. |
| Local `PENDING_APPROVAL` | Từ chối sử dụng sản phẩm, thông báo chờ phê duyệt. | Nếu có trang pending thì chỉ có quyền giới hạn. |
| Đã authenticated/admitted nhưng thiếu quyền tài nguyên | **403 Forbidden** hoặc trang denied. | `AccessDeniedHandler` có thể xử lý. |
| Status DB không sẵn sàng | **Fail closed** và báo lỗi thử lại. | Có thể chọn 503 cho API, không cấp quyền mặc định. |

**Tránh vòng lặp login:** nếu người dùng còn IdP SSO session, redirect từ “local account locked” về IdP ngay sẽ nhận lại SAML assertion hợp lệ rồi lại bị chặn, lặp vô hạn. Thay bằng trang giải thích và hướng dẫn liên hệ admin/approval, không yêu cầu quyền đã bị từ chối. Phải bảo vệ chống user enumeration: thông báo công khai không tiết lộ quá nhiều trạng thái nội bộ khi chưa bảo đảm danh tính.

### 9.1. Audit log tối thiểu

~~~text
event=FEDERATED_LOGIN_DENIED
time_utc=2026-11-07T03:00:00Z
idp_registration=corporate
trusted_issuer=urn:example:idp:corporate
local_account_id=user-42
reason=ACCOUNT_LOCKED
correlation_id=trace-024b
outcome=AUTHENTICATION_FAILURE
~~~

Lưu trace/correlation, policy version, issuer đã xác minh và reason code phục vụ quản trị. Không log toàn bộ SAMLResponse XML, NameID có PII, cookie, private key hoặc chi tiết điều tra bảo mật trong response công khai. Cần xử lý riêng trường hợp account lookup thất bại do `not found` so với `database unavailable` trong log; với người dùng thông báo có thể giống nhau nhưng hệ thống vận hành phải phân biệt.

## 10. Kiểm thử các trường hợp quan trọng

| Test case | Kết quả an toàn |
| --- | --- |
| IdP SAML hợp lệ, local ACTIVE, có quyền vào SP. | Đăng nhập thành công, quyền được map từ approved entitlements. |
| SAML hợp lệ, local account LOCKED. | Không tạo Authentication/session mới. |
| SAML hợp lệ, local account DISABLED. | Từ chối và thu hồi phiên/token cũ theo SLA. |
| SAML hợp lệ, account đang PENDING_APPROVAL. | Không dùng nghiệp vụ; trang chờ duyệt không mở rộng quyền. |
| SAML hợp lệ, không có local account, JIT tắt. | Deny, không tạo tài khoản ngầm. |
| SAML hợp lệ, JIT bật nhưng thiếu phê duyệt/tenant/license. | Không cấp quyền; có thể tạo PENDING nếu chính sách cho phép. |
| SAML hợp lệ, group IdP chứa admin nhưng local bị khóa. | Local deny thắng. |
| ACTIVE nhưng thiếu `reports:read`. | Đăng nhập có thể đạt, resource 403. |
| Có quyền tenant A nhưng gọi API tenant B. | 403, không rò dữ liệu tenant khác. |
| Email đã được tái sử dụng cho danh tính liên kết mới. | Không tự nối vào quyền cũ; dùng verified stable subject. |
| JIT đăng nhập đồng thời ở hai node. | Binding unique, không tạo trùng hay bỏ qua khóa. |
| DB/status store lỗi khi login. | Fail closed, không mặc định ACTIVE. |
| Account bị khóa khi session đang sống. | Phiên không tiếp tục sử dụng vượt SLA revocation. |
| Role bị thu hồi trong phiên. | Authorization lấy trạng thái mới hoặc phiên/token bị thu hồi. |
| SAML response chữ ký sai hoặc `InResponseTo` mismatch. | Từ chối trước khi xét tạo account JIT. |
| IdP vẫn có SSO session sau local lock. | Không tạo login loop, hiển thị trang lỗi an toàn. |

Integration test nên chạy với SAMLResponse đã được ký bởi IdP test và federation metadata chuẩn để chứng minh **đúng thứ tự SAML validation → local admission → session**. Unit test Java policy không thay thế kiểm thử Spring Security filter/provider. Đồng thời test multi-node, stale caches, JIT race, tenant boundaries và revoked sessions.

## 11. Lỗi thường gặp và cách sửa

1. **“IdP xác thực đúng thì ứng dụng bắt buộc cho vào.”** Sai: admission và resource authorization là quyết định của SP.
2. **“Local lock bị bỏ qua nếu IdP group là admin.”** Sai: khóa cục bộ cần ưu tiên cao hơn.
3. **“Chỉ ẩn button bị cấm trên frontend.”** Sai: phải kiểm tra tại API/method.
4. **“Có bean `UserDetailsService` thì SAML login tự xét `isEnabled`.”** Sai: cần nối vào chính SAML flow.
5. **“Email là khóa an toàn duy nhất.”** Sai: email thay đổi/tái dùng; dùng issuer + stable subject.
6. **“Không thấy ACTIVE thì chạy JIT tạo tài khoản mới.”** Sai: có thể bỏ sót account LOCKED/DEPROVISIONED.
7. **“Cứ map tất cả IdP group thành app role.”** Sai: cần allowlist và approval policy.
8. **“Kiểm tra trạng thái một lần tại login là đủ.”** Sai: tài khoản có thể bị khóa khi session còn tồn tại.
9. **“401 cho mọi lỗi thiếu quyền.”** Sai: đã xác thực nhưng thiếu quyền tài nguyên thường là 403.
10. **“Local DB lỗi thì cấp quyền tạm để không ảnh hưởng uptime.”** Sai: phải fail closed cho điều kiện quyền bắt buộc.
11. **“SAML thành công nên khỏi kiểm tra tenant ở backend.”** Sai: dễ gây BOLA/IDOR.
12. **“Redirect liên tục về IdP sẽ khắc phục local locked.”** Sai: gây vòng lặp vì IdP session vẫn hợp lệ.
13. **“Local lock có nghĩa tất cả hệ thống SSO khác đã logout.”** Sai: cần lifecycle/revocation liên hệ IAM.
14. **“`ROLE_USER` tương đương mọi quyền.”** Sai: không cấp quyền nghiệp vụ mặc định ngoài chính sách.

## 12. Checklist triển khai

1. Identity binding gắn **trusted issuer + stable subject + tenant scope** chưa, có chặn email-based merge không?
2. Local account có trạng thái `ACTIVE/LOCKED/DISABLED/PENDING` và rule deny precedence rõ chưa?
3. **Admission check** có chạy sau SAML validation và trước khi tạo `Authentication` không?
4. `NO_LOCAL_ACCOUNT` có bị deny mặc định hoặc JIT với eligibility, unique constraint, audit và least privilege không?
5. Có kiểm tra lịch sử account LOCKED/DISABLED trước JIT để ngăn tái tạo không?
6. Permissions/roles có dựa trên **approved application entitlements**, không tin mọi SAML group không?
7. Mỗi API/service có tenant, ownership và resource-level check độc lập với đăng nhập không?
8. Các session/JWT cũ có bị thu hồi khi account bị khóa trong lúc đã đăng nhập không?
9. SLA revocation có được kiểm thử với multi-node, cache stale và database outage không?
10. Error handler có tránh login loop, user enumeration và lộ PII/SAMLResponse không?
11. Đã kiểm thử local status LOCKED, DISABLED, PENDING, NO_ACCOUNT và ACTIVE thiếu quyền bằng IdP test chưa?
12. Có audit reason code, trusted issuer, local account ID và policy version cho mỗi denial không?

## Tài liệu tham khảo

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses, response authentication converter](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Method Security và @PreAuthorize](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security API — UserDetails.isEnabled và isAccountNonLocked](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security API — AuthenticationManager và ngoại lệ trạng thái account](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
