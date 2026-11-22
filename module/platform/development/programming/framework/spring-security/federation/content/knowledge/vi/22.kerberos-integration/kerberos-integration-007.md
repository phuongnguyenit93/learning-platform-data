# Tải quyền người dùng sau khi xác minh principal Kerberos trong Spring Security

> **Chủ đề:** Spring Security – federation. **Nhóm:** Tích hợp Kerberos. Bài Knowledge này giải thích cách đưa **principal Kerberos đã được GSS/SPNEGO xác minh** vào quy trình tải tài khoản và quyền của Spring Security, với trọng tâm là `KerberosServiceAuthenticationProvider`, `UserDetailsService`, Active Directory/LDAP, database, `GrantedAuthority`, tenant isolation, cache và thu hồi quyền. Các ví dụ Java 17+ phân biệt rõ chương trình độc lập với cấu hình Spring cần Kerberos realm và keytab thực tế.

## 1. Kerberos xác thực người dùng, nhưng chưa cấp quyền nghiệp vụ

Khi trình duyệt thực hiện SPNEGO login thành công, một HTTP service có thể xác minh ticket và biết:

~~~text
Verified client principal:
  alice@EXAMPLE.ORG
Target service:
  HTTP/portal.example.org@EXAMPLE.ORG
Authentication mechanism:
  Kerberos v5 through GSS/SPNEGO
~~~

Điều đó **không tự chứng minh** Alice được phép:
- Xem mọi báo cáo.
- Duyệt giao dịch tài chính.
- Truy cập dữ liệu của tenant khác.
- Sử dụng tài khoản ứng dụng đã bị khóa.
- Nhận quyền quản trị chỉ vì thuộc một Windows domain.
- Giữ quyền sau khi AD group đã bị thu hồi.

**Ranh giới cốt lõi:**
- **Authentication** trả lời: *Danh tính nào đã chứng minh việc sở hữu Kerberos credential hợp lệ?*
- **Identity lookup** trả lời: *Principal này có mapping tới tài khoản nội bộ nào và tài khoản có được sử dụng ứng dụng không?*
- **Authority loading** trả lời: *Từ nhóm, vai trò và policy đã được duyệt, tài khoản được cấp các `GrantedAuthority` nào?*
- **Authorization** trả lời: *Đối với resource và tenant cụ thể, hành động hiện tại có được phép không?*

Spring Security Kerberos có một điểm mở rộng đúng cho thao tác này: `KerberosServiceAuthenticationProvider.setUserDetailsService(UserDetailsService)`. Theo JavaDoc của Spring, provider cần UserDetailsService để tải user properties và `GrantedAuthorities`, vì Kerberos validation về cơ bản đưa lại username/principal chứ không tự cung cấp quyền nghiệp vụ.

## 2. Sơ đồ quy trình: ticket trước, quyền sau

~~~text
Browser / workstation có Kerberos credential cache
       |
       | GET /reports/42
       v
Spring Security protected route
       |
       | 401 Unauthorized
       | WWW-Authenticate: Negotiate
       v
Browser/GSS-API xin service ticket cho HTTP SPN
       |
       | Authorization: Negotiate <GSS token>
       v
SpnegoAuthenticationProcessingFilter
       |
       v
AuthenticationManager / ProviderManager
       |
       v
KerberosServiceAuthenticationProvider
       |
       +-- KerberosTicketValidator
       |      |
       |      +-- Keytab của HTTP service
       |      +-- Ticket/SPN/Authenticator/session key
       |      +-- Time, replay, integrity, realm checks
       |      |
       |      v
       |   Verified principal: alice@EXAMPLE.ORG
       |
       +-- UserDetailsService.loadUserByUsername(principal)
              |
              +-- Trusted local/AD/LDAP identity lookup
              +-- Account active/locked/expired policy
              +-- Group/entitlement lookup
              +-- Stable group ID -> app-role allowlist
              +-- Tenant membership/account mapping
              |
              v
          UserDetails + GrantedAuthority collection
       |
       v
Authenticated Spring Authentication
       |
       v
SecurityContext / AuthorizationFilter / Method Security
       |
       v
Tenant + resource-level decision: ALLOW / DENY
~~~

**Không đảo thứ tự** bằng cách lấy `X-User`, `username` query parameter hoặc một chuỗi được trích từ Base64 chưa xác minh rồi gọi UserDetailsService để tự dựng Authentication.

## 3. Những class Spring Security cần biết

| API | Vai trò |
|---|---|
| `SpnegoEntryPoint` | Phát challenge 401 với `WWW-Authenticate: Negotiate` |
| `SpnegoAuthenticationProcessingFilter` | Nhận HTTP Negotiate token và đưa tới AuthenticationManager |
| `KerberosServiceRequestToken` | Authentication token mang Kerberos/SPNEGO bytes cần xác minh |
| `KerberosTicketValidator` | Interface xử lý Kerberos service ticket |
| `SunJaasKerberosTicketValidator` | JAAS/GSS ticket validator dùng service principal và keytab |
| `KerberosTicketValidation` | Kết quả ticket validation, gồm danh tính đã xác minh theo API |
| `KerberosServiceAuthenticationProvider` | Verify token rồi tải user properties/authorities |
| `UserDetailsService` | Tra user từ verified principal/username |
| `UserDetails` | Account identity, status, authorities |
| `GrantedAuthority` | Một quyền Spring có thể dùng tại authorization |
| `SimpleGrantedAuthority` | Implementation phổ biến cho một authority string |
| `SecurityContextHolder` | Truy cập Spring Authentication hiện hành |
| `AuthorizationManager` | Quyết định quyền ở HTTP/method layers |
| `@PreAuthorize` | Annotation method security dựa vào Authentication |
| `ProviderManager` | Điều phối AuthenticationProvider phù hợp |

**Hai authentication providers khác nhau:**
- `KerberosServiceAuthenticationProvider` xử lý **incoming SPNEGO service ticket**, phù hợp browser Kerberos SSO.
- `KerberosAuthenticationProvider` phục vụ các trường hợp username/password qua Kerberos client. Không cần thêm provider password này chỉ để đọc role sau SPNEGO.
- `ActiveDirectoryLdapAuthenticationProvider` là một authentication provider riêng; nếu chỉ cần lấy AD groups sau Kerberos, có thể dùng directory lookup mà **không yêu cầu user nhập password để LDAP bind lại**.

## 4. Kerberos validator xác minh gì và để lại gì cho ứng dụng?

Trong Kerberos HTTP Negotiate:
1. Browser có TGT hoặc credentials qua OS/SSPI/GSS-API.
2. Client xin service ticket cho SPN, ví dụ `HTTP/portal.example.org@EXAMPLE.ORG`.
3. Browser gửi token có AP-REQ/service ticket và Authenticator.
4. Service dùng keytab để xử lý ticket encrypted part và GSS context.
5. Verifier kiểm cryptographic integrity, session key proof, thời gian, replay và realm/SPN policy.
6. Kết quả có một Kerberos client principal đã được xác thực.

**Kerberos không tự quyết định** tài khoản local đang active, user có app role nào, hoặc user được phép xem report của tenant nào. Service ticket cũng không tự động chứa AD groups theo một hợp đồng portable để Spring map business roles. Mọi business authority phải đến từ **nguồn đã phê duyệt** sau validation.

### 4.1. Có thể tin raw HTTP Negotiate header không?

Chưa. Header chỉ là đầu vào chưa được validate. Phải để framework/GSS xử lý:
- Không Base64 decode rồi tự đọc username.
- Không đọc claim tùy ý trong một token chưa ký/xác minh.
- Không tạo local session trước khi Kerberos provider trả Authentication thành công.
- Không chấp nhận `X-Remote-User` từ client làm Kerberos proof.

Nếu TLS reverse proxy tự verify Kerberos và chỉ chuyển principal header nội bộ, đó là **pre-authenticated architecture khác**, cần mTLS/network isolation/header stripping và riêng trust policy; backend không được tuyên bố đã trực tiếp xác minh Kerberos ticket nếu nó chỉ đọc một header.

## 5. Principal phải giữ realm và danh tính có namespace

Ví dụ hai principal:

~~~text
alice@EXAMPLE.ORG
alice@PARTNERS.ORG
~~~

Hai principal có thể là hai người hoàn toàn khác nhau. Không tự làm:

~~~java
// KHÔNG AN TOÀN trong môi trường có nhiều realm.
String localUserId = verifiedPrincipal.split("@")[0];
~~~

Lý do:
- Kerberos realm là một phần namespace.
- AD `sAMAccountName` không unique trên mọi trusted domains.
- Email, short username, UPN alias có thể thay đổi/tái sử dụng.
- Cross-realm trust cho phép các principals khác realm xác thực ở một số service nhưng **không cấp local app access tự động**.
- Một ứng dụng multi-tenant càng phải tránh ghép user bằng tên ngắn.

### 5.1. External identity key

Nên quy định concept:

~~~text
IdentityLinkKey:
  mechanism = KERBEROS
  trustedRealm = EXAMPLE.ORG
  verifiedPrincipal = alice@EXAMPLE.ORG
  optionalDirectoryObjectId = objectGUID/objectSID
  optionalTenantScope = team-a
~~~

Đây là **mô hình ứng dụng đề xuất**, không phải object Spring mặc định. Một mapping được phê duyệt mới chuyển external identity sang localUserId.

### 5.2. Chuẩn hóa username như thế nào?

- Ưu tiên **exact verified principal** để lookup.
- Nếu có case normalization/realm alias mapping, dựa vào quy tắc KDC/directory được tài liệu hóa, không tự `toLowerCase()` toàn bộ rồi bỏ qua collisions.
- Với AD, có thể tra UPN để tìm objectGUID, objectSID hoặc stable directory ID và dùng ID để nối local account.
- Không tự merge hai realms chỉ vì cùng `alice`.
- Nếu lookup trả nhiều directory entries, **fail closed**, không chọn record đầu tiên.

## 6. UserDetailsService là điểm mở rộng chính

Signature cơ bản:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

Chữ ký này minh họa interface đã có của Spring Security; không cần khai báo mới trong project.

Trong tích hợp Kerberos:
- `username` là tên được ticket validator xác minh, ví dụ `alice@EXAMPLE.ORG`.
- UserDetailsService truy vấn account và quyền, trả `UserDetails` có `getAuthorities()`.
- `KerberosServiceAuthenticationProvider` phối hợp validator và UserDetailsService trong authentication pipeline.
- Nếu principal không được provisioned, `UsernameNotFoundException` là một đường từ chối phù hợp.
- Nếu directory lỗi, không fallback tự cấp quyền mạnh; giữ nguyên lỗi/fail closed theo chính sách.

### 6.1. UserDetailsService không xác thực Kerberos

Nó không cần:
- User password.
- TGT của người dùng.
- File keytab của service để đọc groups.
- Raw SPNEGO token.
- SAML Assertion, JWT hay claims OIDC.

Kerberos verifier chịu trách nhiệm authentication; UserDetailsService chịu trách nhiệm lookup identity/authorities. Việc directory API dùng LDAP credentials riêng hoặc Kerberos SASL bind là vấn đề kết nối tới directory, **khác** việc xác minh HTTP ticket.

### 6.2. Account status phải được thực thi rõ

Kết quả lookup nên có policy cho:
- Account missing.
- Account disabled/suspended.
- Account locked.
- Account expired.
- Local identity link bị revoke.
- Tenant membership disabled.
- Quyền chưa được cấp.
- Quyền từng có nhưng đã hết hiệu lực.

Không mặc định mọi Kerberos provider luôn gọi tất cả checkers giống `DaoAuthenticationProvider`. Để an toàn, service/policy có thể **từ chối ngay trong UserDetailsService** khi account bị disable/locked, và có integration tests với version Kerberos thực tế. Nếu provider có native account checks thì dùng đúng extension point thay vì giả định.

## 7. Nguồn lấy quyền sau Kerberos

| Nguồn | Thông tin thích hợp | Lưu ý |
|---|---|---|
| Local relational DB | Local user ID, roles, tenant memberships, account status | Indexed exact identity key, unique constraints |
| Active Directory | objectSID/objectGUID, memberships, account flags | Nested group, trust forest, stable identifiers |
| LDAP directory | Groups, attrs, application directory user | LDAP schema và escaping/LDAPS riêng |
| IAM/entitlement API | Roles, permissions, policy version | Trusted service authentication/availability |
| Cached roles | Snapshot quyền trong TTL | Revocation/invalidation rõ |
| In-memory fixture | Demo/test | Không phải nguồn quyền production |
| HTTP request headers | Không phải nguồn cấp role trực tiếp | Client spoofing risk |
| Kerberos ticket bytes | Chỉ authentication proof, không business role source | GSS validation bắt buộc |

**Đặc biệt:** Nếu quyền do ứng dụng kiểm soát, không nhất thiết mọi app role đều phải xuất phát từ AD group. Có thể dùng AD để định danh người dùng, còn quyền phê duyệt báo cáo nằm trong database.

## 8. Group-to-authority mapping phải có allowlist

Ví dụ authoritative policy:

| Trusted realm | Directory group stable ID | Tenant | Spring authority |
|---|---|---|---|
| EXAMPLE.ORG | G-REPORT-READ | team-a | ROLE_REPORT_VIEW |
| EXAMPLE.ORG | G-REPORT-APPROVE | team-a | ROLE_REPORT_APPROVE |
| EXAMPLE.ORG | G-FINANCE-READ | finance | ROLE_FINANCE_VIEW |
| PARTNERS.ORG | Nhóm tên gần giống | team-a | Không cấp mặc định |
| Bất kỳ realm khác | Chuỗi ROLE_ADMIN do client khai | Bất kỳ | Không cấp |

Một tên AD group `GG-FinanceReaders` không phải tự nhiên là `ROLE_ADMIN` hay `ROLE_REPORT_VIEW`. Dùng **stable group SID/ID** khi có thể, vì display name có thể đổi/trùng. Chỉ những group/role được quản trị phê duyệt mới được map.

### 8.1. Không copy mọi LDAP group thành GrantedAuthority

Anti-pattern:

~~~java
// KHÔNG AN TOÀN: tin mọi group text là quyền ứng dụng.
String role = "ROLE_" + ldapGroupName;
GrantedAuthority grant = new SimpleGrantedAuthority(role);
~~~

Nếu group name chứa “Admin” hay được đổi tên bất ngờ, quyền có thể sai. Cần exact-ID mapping đã duyệt, scope realm/tenant và không cấp quyền khi không match.

### 8.2. Nested groups trong AD

Một user có thể thuộc nhóm A, nhóm A nằm trong nhóm B. Truy vấn `memberOf` trực tiếp có thể không trả mọi effective membership theo cách ứng dụng mong muốn. Hãy xác định:
- Có cần transitive groups hay không.
- Dùng `tokenGroups`, matching-rule-in-chain, hoặc IAM source đã tính memberships.
- Cross-domain/cross-forest trusted groups được xử lý thế nào.
- Group SID và principal đã được bind với realm/tenant phù hợp không.
- Giới hạn truy vấn, timeout, cycles và cache behavior.

Tránh tự suy quyền từ một string danh sách nhóm được browser gửi.

## 9. Phân biệt Authentication với Authorization ở Spring

### 9.1. hasAuthority

~~~java
.requestMatchers("/reports/**")
    .hasAuthority("ROLE_REPORT_VIEW")
~~~

Spring kiểm chính xác authority string trong Authentication.

### 9.2. hasRole

~~~java
.requestMatchers("/reports/**")
    .hasRole("REPORT_VIEW")
~~~

Với role prefix mặc định, `hasRole("REPORT_VIEW")` thường cần authority `ROLE_REPORT_VIEW`. Không truyền `hasRole("ROLE_REPORT_VIEW")` khi prefix mặc định có thể thêm lần nữa. Nếu project thay role prefix, dùng policy nhất quán và kiểm tests.

### 9.3. Resource-level authorization

Một user có `ROLE_REPORT_VIEW` chưa chắc được xem mọi report. Ứng dụng cần kiểm:
- Report thuộc tenant nào?
- User có active membership tenant đó?
- Resource owner/classification/access level?
- Quyền READ có bị giới hạn bởi phòng ban hoặc dự án?
- Có yêu cầu step-up/MFA/fresh login cho thao tác cụ thể?
- Local account hoặc entitlement vừa bị revoke?

Với method security:
~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public ReportDto getReport(String tenantId, String reportId) {
    // Method fragment: cần repository, authorizer, types thật.
    return reportService.getOnlyIfAuthorized(tenantId, reportId);
}
~~~

Điểm quan trọng: phần `getOnlyIfAuthorized` **phải kiểm resource tenant và quyền cụ thể**; method annotation chỉ là một lớp kiểm sơ bộ.

## 10. Java 17 độc lập: mô phỏng authority lookup an toàn

Chương trình dưới đây **chạy bằng JDK 17+ mà không cần Spring/KDC**. Nó giả định verified principal đã được xác minh trước đó, rồi tải local account và map group allowlist sang quyền. Mục đích là làm rõ business authorization, **không thay ticket validation**.

Tệp `KerberosAuthorityDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class KerberosAuthorityDemo {

    record Account(
            String principal,
            String tenant,
            boolean active,
            Set<String> groups) {
    }

    private static final Map<String, Account> ACCOUNTS = Map.of(
            "alice@EXAMPLE.ORG",
            new Account("alice@EXAMPLE.ORG", "team-a", true,
                    Set.of("G-READ", "UNTRUSTED-ADMIN")),
            "bob@EXAMPLE.ORG",
            new Account("bob@EXAMPLE.ORG", "team-a", false,
                    Set.of("G-APPROVE"))
    );

    private static final Map<String, String> GROUP_ROLES = Map.of(
            "G-READ", "ROLE_REPORT_VIEW",
            "G-APPROVE", "ROLE_REPORT_APPROVE"
    );

    static Set<String> authorities(
            String verifiedPrincipal, String trustedTenant) {
        Account a = ACCOUNTS.get(verifiedPrincipal);
        if (a == null || !a.active()
                || !a.tenant().equals(trustedTenant)) {
            return Set.of();
        }
        return a.groups().stream()
                .map(GROUP_ROLES::get)
                .filter(s -> s != null)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    public static void main(String[] args) {
        System.out.println("alice-read="
                + authorities("alice@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_REPORT_VIEW"));
        System.out.println("alice-admin="
                + authorities("alice@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_ADMIN"));
        System.out.println("bob-approve="
                + authorities("bob@EXAMPLE.ORG", "team-a")
                    .contains("ROLE_REPORT_APPROVE"));
        System.out.println("cross-tenant="
                + authorities("alice@EXAMPLE.ORG", "team-b")
                    .contains("ROLE_REPORT_VIEW"));
        System.out.println("other-realm="
                + authorities("alice@PARTNERS.ORG", "team-a")
                    .contains("ROLE_REPORT_VIEW"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac KerberosAuthorityDemo.java
java KerberosAuthorityDemo
~~~

**Stdout chính xác:**

~~~text
alice-read=true
alice-admin=false
bob-approve=false
cross-tenant=false
other-realm=false
~~~

**Giải thích:**
1. Alice có group G-READ đã được phê duyệt nên nhận quyền xem report.
2. Group `UNTRUSTED-ADMIN` không nằm trong allowlist, không tự thành ROLE_ADMIN.
3. Bob có group approve nhưng account không active, nên không có quyền.
4. Tenant team-b khác tenant account đã xác định, không có quyền.
5. Cùng tên ngắn alice nhưng khác Kerberos realm thì không match identity.

**Giới hạn:** Chương trình không xác minh AP-REQ, không đọc keytab và không được dùng `authorities(...)` để tạo authenticated session từ một HTTP parameter. Nó chỉ mô tả lookup **sau** authentication. Không in Set ra stdout để tránh phụ thuộc thứ tự hash iteration.

## 11. Spring Security Kerberos: cấu hình provider và user lookup

Bài học dùng Servlet application có dependency Spring Security Kerberos tương thích Spring Security Core. Các class dưới đây là **integration code**, không chạy độc lập bằng `javac` vì còn framework jars, KDC, keytab, HTTP SPN và browser Kerberos config.

Tệp `src/main/java/com/example/security/KerberosSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(new FileSystemResource(
                "/run/secrets/portal-http.keytab"));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {
        AuthenticationManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
                new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/reports/**")
                    .hasAuthority("ROLE_REPORT_VIEW")
                .requestMatchers("/approve/**")
                    .hasAuthority("ROLE_REPORT_APPROVE")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationManager(manager)
            .addFilterBefore(filter, BasicAuthenticationFilter.class)
            .build();
    }
}
~~~

### 11.1. Phân tích cấu hình

- `SunJaasKerberosTicketValidator` là cryptographic verifier, dùng keytab **của service HTTP**, không dùng user password.
- `KerberosServiceAuthenticationProvider.setUserDetailsService` là phần **tải quyền sau Kerberos validation**.
- `SpnegoAuthenticationProcessingFilter` đọc Negotiate token, không đọc role request parameters.
- `SpnegoEntryPoint` challenge user chưa có authentication.
- `ProviderManager` có provider cho Kerberos service token.
- `SecurityFilterChain` kiểm authorities theo HTTP path.
- Code cố ý không thêm DaoAuthenticationProvider/form password login; nếu dự án cần fallback, phải thiết kế một flow khác có bảo mật riêng.
- Filter được khởi tạo bên trong SecurityFilterChain, tránh đăng ký cùng một Servlet Filter hai lần do Spring Boot tự scan Bean Filter.
- Cần test Spring Security/Spring Security Kerberos release đang chạy, nhất là filter ordering và SecurityContext persistence.

### 11.2. Dependencies Maven

Đây là fragment trong POM đã có Spring Boot parent/BOM; không phải POM độc lập:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

Phiên bản Spring Security Kerberos module và Spring Core/Boot phải tương thích; không chốt tùy tiện một version. Cần keytab secret mount, KDC, realm/DNS/clock config, SPN service account và browser policy mới chạy được end-to-end. Không đưa keytab vào Git hoặc image public.

## 12. Triển khai UserDetailsService kiểm tài khoản rồi ánh xạ quyền

Ví dụ class độc lập trong project Spring Security, nhận một interface repository để không hardcode DB schema. Đây là **mẫu Java code đầy đủ ở cấp class**, còn repository implementation và integration KDC là phần phụ thuộc runtime.

Tệp `src/main/java/com/example/security/KerberosUsers.java`:

~~~java
package com.example.security;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class KerberosUsers implements UserDetailsService {

    public record Account(
            String fullPrincipal,
            boolean active,
            Set<String> directoryGroups) {
    }

    public interface AccountRepository {
        Account findExactPrincipal(String verifiedPrincipal);
    }

    private static final Map<String, String> GROUP_ROLE = Map.of(
            "G-READ", "ROLE_REPORT_VIEW",
            "G-APPROVE", "ROLE_REPORT_APPROVE");

    private final AccountRepository repository;

    public KerberosUsers(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String principal) {
        if (principal == null || principal.isBlank()) {
            throw new UsernameNotFoundException("Invalid Kerberos principal");
        }

        Account account = repository.findExactPrincipal(principal);
        if (account == null || !account.active()
                || !principal.equals(account.fullPrincipal())) {
            throw new UsernameNotFoundException(
                    "Identity not provisioned or account disabled");
        }

        if (account.directoryGroups() == null) {
            throw new UsernameNotFoundException("Group source unavailable");
        }

        List<GrantedAuthority> grants = account.directoryGroups().stream()
                .map(GROUP_ROLE::get)
                .filter(role -> role != null)
                .distinct()
                .map(role -> (GrantedAuthority)
                        new SimpleGrantedAuthority(role))
                .toList();

        return new KerberosOnlyUser(principal, grants);
    }

    private record KerberosOnlyUser(
            String username,
            List<GrantedAuthority> authorities)
            implements UserDetails {

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return null;
        }

        @Override
        public List<GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public boolean isAccountNonExpired() {
            return true;
        }

        @Override
        public boolean isAccountNonLocked() {
            return true;
        }

        @Override
        public boolean isCredentialsNonExpired() {
            return true;
        }

        @Override
        public boolean isEnabled() {
            return true;
        }
    }
}
~~~

### 12.1. Các điểm bảo mật của mã

- `findExactPrincipal` phải được implement bằng trusted directory/DB lookup, giữ realm. Nó không lấy principal do browser tự khai.
- Không có account hoặc account disabled → reject ngay. Đừng chờ một provider chưa được chứng minh có checker giống DaoAuthenticationProvider.
- `directoryGroups` null đại diện **lookup nguồn quyền không khả dụng**, không được coi là mọi group đều được cấp.
- Chỉ groups trong `GROUP_ROLE` mới thành authorities.
- `getPassword()` trả null vì UserDetails được dùng **sau Kerberos ticket validation**, không để thực hiện login bằng mật khẩu. Không đưa object này vào DaoAuthenticationProvider.
- Các cờ isAccountNonLocked/isAccountNonExpired trả true trong demo **vì repository model chỉ có active**. Khi production có locked/expired fields phải kiểm đầy đủ trước khi trả UserDetails; không bỏ qua account lifecycle.
- Code không xét tenant vì interface `UserDetailsService.loadUserByUsername` chỉ có username; tenant-scoped authorization phải được xử lý riêng theo trusted membership/resource scope.
- Nếu app muốn JIT provisioning, đó là một workflow có policy/approval riêng; không bật auto-create trong method này bằng mọi principal Kerberos.
- Mẫu không có Spring @Component, cần bean wiring từ configuration/project.

### 12.2. Bean wiring ví dụ

~~~java
@Bean
UserDetailsService userDetailsService() {
    KerberosUsers.AccountRepository repository = principal -> {
        if ("alice@EXAMPLE.ORG".equals(principal)) {
            return new KerberosUsers.Account(
                    principal, true, Set.of("G-READ"));
        }
        return null;
    };
    return new KerberosUsers(repository);
}
~~~

Đây là **method fragment** trong Spring `@Configuration` có imports phù hợp. Nó dùng allowlist in-memory để học API; production nên inject repository tra DB/AD/LDAP/IAM. Không giữ danh sách user thật trong source.

## 13. LDAP/Active Directory lookup sau Kerberos ticket

### 13.1. Directory lookup khác LDAP password authentication

Khi Kerberos đã xác minh principal, ứng dụng có thể dùng:
- LDAP/LDAPS query bằng read-only directory service account.
- SASL/GSSAPI bind bằng service identity được cấu hình đúng.
- IAM directory API để lấy group memberships.
- DB mapping chứa stable AD object IDs và app roles.

**Không cần lấy user password để LDAP bind lại** chỉ nhằm tải groups. Nếu dùng ActiveDirectoryLdapAuthenticationProvider làm password authentication fallback, hãy tách rõ hai flows và không trộn role maps bừa bãi.

### 13.2. Mapping principal tới stable AD identity

Với Active Directory:
- `userPrincipalName` thường chứa UPN, nhưng có thể thay đổi theo admin policy.
- `sAMAccountName` chỉ unique trong domain scope, dễ trùng giữa domains.
- `objectGUID` là stable directory object ID hữu ích khi rename.
- `objectSid` có thể làm stable security ID cho account/group.
- Group authorization nên ưu tiên stable SID/ID thay vì displayName.
- Cross-domain/forest trust phải được xét trước khi liên kết principal.

### 13.3. LDAP filter phải escape hoặc parameterize

Anti-pattern:

~~~java
// KHÔNG AN TOÀN: nối thẳng principal vào LDAP filter.
String filter = "(userPrincipalName=" + principal + ")";
~~~

Dù principal đến từ trusted GSS context, phải escape khi đưa vào LDAP query; không có input nào tự miễn điều kiện injection. Dùng LDAP API parameter binding/filter escaping, giới hạn search base và kiểm **chính xác một** matching account. SQL cũng phải dùng prepared statements.

### 13.4. Nested group memberships

AD `memberOf` không luôn đại diện mọi effective group memberships trong nested groups/foreign trusts. Cần quyết định:
- Chỉ direct groups hay transitive groups?
- `tokenGroups`/matching-rule-in-chain có hỗ trợ trong directory và được phép đọc không?
- Group caching/TTL?
- SID mapping theo tenant/realm nào?
- Vai trò khi group hoặc user đã bị xóa?
- Directory timeout có làm login fail closed không?

Không tự suy quyền từ một giá trị group name xuất hiện ở bất kỳ nơi nào của directory.

## 14. Database / IAM làm nguồn quyền ứng dụng

Một thiết kế có thể có các bảng:

~~~text
external_identity_link:
    mechanism = KERBEROS
    realm = EXAMPLE.ORG
    full_principal = alice@EXAMPLE.ORG
    local_user_id = 1001
    approved = true

local_user:
    id = 1001
    enabled = true
    locked = false

tenant_membership:
    user_id = 1001
    tenant_id = team-a
    enabled = true

role_assignment:
    user_id = 1001
    tenant_id = team-a
    authority = ROLE_REPORT_VIEW
~~~

Từ verified Kerberos principal:
1. Lookup exact identity link.
2. Kiểm linked account đã approved.
3. Kiểm user active/locked/expired.
4. Load groups/roles từ authoritative source.
5. Áp tenant membership và policy.
6. Trả authorities phù hợp.
7. Khi truy cập tài nguyên, kiểm local user + tenant + resource.

Đây là **schema concept**, không phải SQL migration. Production nên có unique constraints và index cho identity key, audit các thay đổi role và transaction/snapshot consistency.

## 15. Multi-tenant authorization: không chỉ có ROLE_REPORT_VIEW

Ví dụ principal Alice được quyền report-view trong tenant team-a nhưng không thuộc team-b. Nếu Authentication của Alice có global `ROLE_REPORT_VIEW`, gọi:

~~~text
GET /tenants/team-b/reports/42
~~~

phải bị từ chối ở **resource authorization**.

Một cách triển khai là giữ:
- Local user ID đã mapping.
- Set tenant memberships theo chính sách.
- Role assignments có tenant scope.
- Domain service kiểm xem resource thuộc tenant nào.

Không lấy tenant từ `X-Tenant` hay query parameter rồi tự thêm authority vào Spring Authentication. Đặc biệt, `loadUserByUsername(String)` chỉ nhận username, không nhận arbitrary HttpServletRequest; nếu cần tenant trong login, phải có trusted routing/provider context đã được chứng minh, không dùng ThreadLocal client-controlled.

### 15.1. Tại sao @PreAuthorize chưa đủ?

~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public Report getReport(String tenant, String reportId) {
    return reportPolicy.readOnlyIfAllowed(tenant, reportId);
}
~~~

Đây là method fragment, cần implementation và imports. Authorization domain layer phải kiểm owner/tenant, không chỉ dựa vào role. User authenticated vẫn có thể bị HTTP 403 khi chưa có quyền vào resource.

### 15.2. Bật method security

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Tệp là class fragment Java hợp lệ khi có imports `Configuration` và `EnableMethodSecurity`, đặt trong Spring Boot configuration. Không kích hoạt method authorization chỉ bằng việc định nghĩa một method annotation nếu chưa bật cơ chế tương ứng.

## 16. Vai trò trong Session, Cache và vấn đề quyền bị thu hồi

### 16.1. Snapshot quyền

Spring Authentication thường giữ một **snapshot authorities** tại thời điểm login/lookup. Những requests tiếp theo trong cùng HttpSession có thể **không** chạy lại UserDetailsService.

Ví dụ:
- 09:00 Alice login, group approve vẫn còn, Authentication có ROLE_REPORT_APPROVE.
- 10:00 admin gỡ group approve ở AD.
- 10:01 Alice vẫn có local session cũ và có thể thấy authority cũ nếu app không refresh.
- Chỉ đổi AD groups không tự vô hiệu hóa mọi Kerberos ticket và Spring session.

### 16.2. Ba tầng cache

| Cache | Dữ liệu | Rủi ro |
|---|---|---|
| OS Kerberos ticket cache | TGT/ST | Ticket vẫn còn sau thay đổi roles |
| Directory/IAM cache | Groups, role mappings | Membership mới chưa được cập nhật |
| Spring HttpSession/SecurityContext | GrantedAuthorities snapshot | Old authority tiếp tục tồn tại |

**Tách Kerberos ticket expiration khỏi authority expiration**. Renew ticket hoặc password change không bảo đảm application role snapshot tự mới.

### 16.3. Chính sách revoke

Các lựa chọn:
1. TTL authority cache hợp risk level.
2. Event-driven invalidation khi IAM/AD membership đổi.
3. Invalidate Spring sessions khi quyền bị revoke hoặc local account bị disable.
4. Kiểm entitlement live với thao tác đặc biệt nhạy cảm.
5. Redis/shared session state theo cluster và revocation version.
6. Không dùng cache vô hạn cho ROLE_ADMIN.
7. Nếu directory outage, fail closed cho login/role elevation; stale read cần policy explicit.
8. Có audit ai cấp/thu hồi quyền và khi nào role snapshot được tạo.

### 16.4. Nếu AD/LDAP không phản hồi?

Không tạo fallback user với ROLE_ADMIN và không giả vờ người dùng thuộc mọi nhóm. Tùy product policy:
- Từ chối login và báo lỗi tạm thời (khác invalid ticket).
- Dùng cache có TTL rất cụ thể cho low-risk read-only access nếu được phê duyệt.
- Chặn các tác vụ nhạy cảm cho đến khi source IAM có sẵn.
- Áp timeout, circuit breaker, quan sát latency và tránh treo servlet threads.

## 17. JIT provisioning và account linking

Một Kerberos principal hợp lệ nhưng chưa có local record có thể gặp hai chính sách:

**Pre-provisioned:** chỉ những users được admin tạo trước có quyền login. User không tồn tại → reject.

**Just-In-Time:** ứng dụng tự tạo local account khi có verified Kerberos identity, nhưng chỉ khi:
- Realm/SPN/user thuộc allowlist.
- IAM/group onboarding entitlement được phê duyệt.
- Không va chạm với account/local identity link khác.
- Tenant membership được xác định server-side.
- Default quyền ít nhất, không phải ROLE_ADMIN.
- Có audit và khả năng offboarding/disable.

Đừng tự link vào user cũ chỉ vì cùng email hoặc short name. Việc identity linking cần proof và audit, nhất là khi nhiều forests/realms được trust.

## 18. Khi account disabled, ticket vẫn có thể hợp lệ

Kerberos Service Ticket đã được KDC phát trước lúc user bị khóa có thể còn hợp lệ trong ticket lifetime. GSS verifier có thể tiếp tục trả verified principal theo protocol/policy. Vì vậy:
- App phải kiểm local account enabled/locked/offboarded.
- Các business roles cần revocation theo deadline.
- Đừng chỉ kiểm `isAuthenticated()` hoặc principal suffix.
- Nếu provider không tự thực thi mọi UserDetails flags, hãy reject ngay ở service/policy đã được test.
- Session đã tồn tại cần bị invalidated khi khóa user theo yêu cầu an ninh.

**Không đồng nhất:** Kerberos authentication success với application account eligible.

## 19. LDAP group và local role có thể xung đột

Giả sử:
- AD group cho Alice quyền report-read.
- Local DB role assignment lại đã bị revoke.
- App business policy là quyền được phép chỉ khi **cả** directory membership và local tenant membership active.

Đừng gộp hai nguồn theo kiểu union tất cả quyền mà chưa quy định precedence. Phải có explicit rule:
- Directory source quy định danh tính/group thuộc tổ chức.
- App source quy định role/tenant entitlement.
- Với quyền nhạy cảm, cần conjunction/approval.
- Khi một source mất, fail closed hoặc theo quy trình offline đã được duyệt.
- Nếu hai nguồn mâu thuẫn, deny và audit thay vì chọn bên cho nhiều quyền hơn.

**Điểm học tập:** Tải quyền không chỉ là truy vấn group, mà là thực hiện **policy decision** với trust và lifecycle rõ.

## 20. Kiểm thử unit và integration

### 20.1. Unit tests cho mapper

| Case | Input | Kỳ vọng |
|---|---|---|
| U1 | Verified Alice active, G-READ | ROLE_REPORT_VIEW |
| U2 | Alice có group lạ mang tên Admin | Không cấp ROLE_ADMIN |
| U3 | Bob disabled nhưng G-APPROVE | Deny |
| U4 | User ở team-a truy cập team-b | Deny |
| U5 | Same short name, khác realm | Không link nhầm |
| U6 | Directory không tìm thấy user | UsernameNotFoundException |
| U7 | Directory có hai matches | Deny ambiguous |
| U8 | Group ID null/format sai | Reject/ignore theo contract |
| U9 | Account expired/locked | Deny |
| U10 | Duplicate groups | Không tạo duplicate authorities |
| U11 | Realm không được phép | Deny |
| U12 | Group list lỗi do timeout | Không tự cấp quyền |
| U13 | User không có roles | No-access hoặc guest policy đã duyệt |
| U14 | Principal chứa ký tự LDAP filter đặc biệt | Query escaped/parameterized |
| U15 | Tenant membership revoked | Deny ở resource layer |

### 20.2. Integration tests cho Kerberos pipeline

1. Browser gửi valid SPNEGO token cho đúng HTTP SPN.
2. `SunJaasKerberosTicketValidator` verify ticket bằng keytab.
3. Provider lấy đúng principal (gồm realm).
4. `UserDetailsService.loadUserByUsername` được gọi **sau** ticket validation.
5. User account active có authorities theo allowlist.
6. Route `/reports/**` được phép khi có ROLE_REPORT_VIEW.
7. Route `/approve/**` bị 403 nếu không có ROLE_REPORT_APPROVE.
8. Wrong SPN, stale keytab, replay và wrong realm đều bị từ chối.
9. Không có directory account thì không cấp local authenticated business role.
10. Active session dùng cached authorities được test khi quyền đổi.
11. Directory outage không dẫn đến admin fallback.
12. Nested groups/cross-forest trusts đúng policy.
13. Proxy/ingress không cho browser tự đặt trusted identity headers.
14. Load balancer nodes nhất quán keytab và IAM policy.
15. CSRF/TLS và session fixation protection vẫn hoạt động.

**Chỉ dùng MockMvc với mock principal không chứng minh Kerberos ticket validation.** Cần integration test KDC/GSS/HTTP Negotiate thật để xác minh trust boundary.

## 21. Troubleshooting: 401, 403 và quyền thiếu

| Triệu chứng | Tầng lỗi thường gặp | Hướng kiểm |
|---|---|---|
| 401 không có Negotiate challenge | SecurityFilterChain/entrypoint | Filter order, route, 401 header |
| 401 với token SPNEGO | GSS/Kerberos verification | SPN, keytab, kvno, realm, clocks |
| Kerberos pass nhưng UsernameNotFound | User mapping | Full principal, AD/DB identity link |
| Kerberos pass nhưng 403 | Authorization | GrantedAuthorities, role/tenant |
| `hasRole("ROLE_REPORT_VIEW")` sai | Role prefix | Dùng hasRole("REPORT_VIEW") hoặc hasAuthority |
| Nhóm mới chưa thành role | Group mapping/cache | Stable SID, nested membership, refresh |
| Nhóm bị xóa nhưng role vẫn còn | Session/cache stale | Invalidation, entitlement recheck |
| LDAP trả nhiều user | Search base/filter quá rộng | Narrow scope, reject ambiguous |
| AD account disabled nhưng user vẫn vào được | Chưa kiểm app status/session | Reject disabled + session revoke |
| Username Alice ở realm khác được nhầm | Bỏ realm/UPN alias sai | Exact principal/identity link |
| LDAP lookup lâu hoặc timeout | Directory backend | TLS, network, timeout, circuit breaker |
| Role admin cấp cho mọi domain user | Policy mapping lỗi | Allowlist, no default elevation |
| GSS token đúng nhưng tenant bị sai | Resource authorization thiếu | Tenant memberships and IDOR checks |
| Chỉ lỗi ở một node | Keytab/cache/policy khác phiên bản | So deployment mỗi node |
| Login khác flow vẫn được | Provider mix-up | Kiểm AuthenticationManager và filter chain |
| HTTP Negotiate là NTLM | SPNEGO mechanism fallback | Enforce approved mechanism |
| User vừa đổi password mà vẫn có ticket | Kerberos credential lifecycle | Không nhầm ticket và roles |

**Thứ tự debug:** browser Negotiate → GSS/SPN/keytab → verified principal/realm → UserDetailsService → account state → group-to-role policy → Authentication.getAuthorities → tenant/resource authorization → cache/session revocation.

## 22. An toàn vận hành

- Không log raw `Authorization: Negotiate` token, TGT/ST, session key, keytab hoặc LDAP bind password.
- Bảo vệ keytab bằng secret store/volume và file ACL chỉ cho service UID.
- Bật TLS/HTTPS dù đã có Kerberos; Kerberos không bảo vệ toàn bộ HTTP body.
- Giữ CSRF protection cho state-changing requests.
- LDAP/AD lookup dùng LDAPS/StartTLS hoặc kết nối bảo mật tương đương, service account least privilege.
- Áp escape/parameterized filter/SQL để ngăn injection.
- Nếu Spring session giữ authorities, phải có quy trình revoke khi IAM role đổi.
- Không suy ROLE_ADMIN từ AD Domain Users hoặc realm membership.
- Ghi audit trạng thái login/lookup/deny theo correlation ID, không lộ PII quá mức.
- Không dùng ticket để xác minh account status vì ticket có lifetime riêng.
- Không copy incoming Negotiate token sang backend SPN khác; delegation cần thiết kế và cấp quyền riêng.
- Chốt versions Spring Security, Spring Security Kerberos và Java/Jakarta Servlet phù hợp với code đang chạy.

## 23. Checklist hoàn thành

- [ ] User principal được xác minh bằng Kerberos GSS trước quyền lookup.
- [ ] Spring Kerberos provider được gắn UserDetailsService bằng `setUserDetailsService`.
- [ ] Có identity mapping giữ full principal và realm.
- [ ] Account missing/disabled/locked/expired bị reject.
- [ ] Directory/DB/IAM là nguồn authorities đáng tin, không lấy từ browser.
- [ ] AD groups được map bằng stable group ID/SID và explicit allowlist.
- [ ] No default ROLE_ADMIN hoặc auto grant từ tên realm.
- [ ] Role prefix và hasRole/hasAuthority được dùng đúng.
- [ ] Business resource checks giới hạn tenant và owner.
- [ ] Có TTL/invalidation cho directory cache và Spring sessions.
- [ ] Đã test offboarding/revoke và group updates.
- [ ] LDAP/SQL queries được parameterized và TLS bảo vệ.
- [ ] Có integration tests với Kerberos/Keytab/KDC thật.
- [ ] Không làm yếu CSRF/TLS/session management vì có SPNEGO.
- [ ] Không log raw tickets, keytab hoặc directory secrets.
- [ ] Cross-realm principal và short-name collisions đã được kiểm.
- [ ] Có kịch bản outage của nguồn quyền với fail-closed policy.

## 24. Câu hỏi ôn tập

1. **Kerberos ticket chứng minh gì?** Client principal đã thực hiện Kerberos AP exchange hợp lệ theo trust policy, không tự cấp app role.
2. **Spring API dùng để tải quyền sau ticket validation?** `KerberosServiceAuthenticationProvider.setUserDetailsService`.
3. **UserDetailsService có xác minh keytab không?** Không, validator/GSS làm việc đó.
4. **Vì sao UserDetailsService cần username đã verified?** Tránh client giả identity qua header hoặc query.
5. **Tại sao không bỏ realm khỏi principal?** Có thể trùng username giữa trusted realms.
6. **Group AD có tự là ROLE_ADMIN không?** Không; phải map theo policy.
7. **hasRole("REPORT_VIEW") khác hasAuthority("ROLE_REPORT_VIEW") thế nào?** Với prefix mặc định, cùng authority được yêu cầu.
8. **Account disabled nhưng ticket còn hạn có được login không?** Không nếu app policy từ chối.
9. **Role thay đổi ở AD có làm Spring session tự cập nhật không?** Không mặc định, có cache/session snapshot.
10. **Tại sao dùng group SID thay group displayName?** SID ổn định hơn và tránh nhầm tên.
11. **LDAP directory lookup cần user password không?** Không, có thể dùng service identity và directory read policy.
12. **AD nested groups có cần chính sách riêng không?** Có, memberOf trực tiếp có thể chưa đủ.
13. **Một user thuộc team-a có thể đọc report team-b vì có ROLE_REPORT_VIEW không?** Không; resource-level tenant check.
14. **Khi nguồn quyền timeout nên làm gì?** Fail closed hoặc dùng cache có TTL được phê duyệt, không cấp quyền lớn.
15. **JIT provisioning có được tự tạo admin cho mọi Kerberos user không?** Không.
16. **MockMvc user() có chứng minh SPNEGO ticket validation không?** Không.
17. **Kerberos login 401 khác 403 thế nào?** 401 thường authentication challenge/failure; 403 thường đã có identity nhưng thiếu quyền.
18. **Nếu app đọc X-Remote-User từ proxy thì sao?** Đó là preauth architecture khác, phải có trusted gateway và strip client headers.
19. **Khi quyền bị thu hồi, cần xử lý gì ngoài AD group?** Role cache, Spring sessions và resource policy.
20. **Nguyên tắc bao trùm?** Verify Kerberos trước, link account đáng tin, map quyền theo allowlist và kiểm tenant/resource tại điểm sử dụng.

## 25. Tài liệu tham khảo chính thức

- Spring Security Kerberos — JavaConfig, SPNEGO and AuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security Kerberos — KerberosServiceAuthenticationProvider JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- Spring Security Kerberos — SpnegoAuthenticationProcessingFilter JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — GrantedAuthority và HTTP authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — LDAP/AD directory authentication reference: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Kerberos v5, RFC 4120: https://www.rfc-editor.org/rfc/rfc4120
- HTTP SPNEGO/Negotiate, RFC 4559: https://www.rfc-editor.org/rfc/rfc4559
- SPNEGO GSS-API mechanism, RFC 4178: https://www.rfc-editor.org/rfc/rfc4178
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — LDAP Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html

**Kết luận:** Kerberos/SPNEGO giải bài toán **“Ai đã được KDC xác thực?”**. `UserDetailsService` sau `KerberosServiceAuthenticationProvider` giải bài toán **“Tài khoản ứng dụng tương ứng là ai và được cấp những GrantedAuthority nào?”**. Cuối cùng, Spring Authorization và business services quyết định **“Người đó có được thực hiện hành động với resource/tenant cụ thể không?”**. Giữ nguyên realm và verified principal, fail closed khi identity/group lookup mơ hồ, không cấp quyền từ ticket hoặc browser header, và quản lý cache/thu hồi quyền rõ ràng sẽ giúp tích hợp Kerberos đúng cả về authentication lẫn authorization.
