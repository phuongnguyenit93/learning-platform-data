# Liên kết danh tính nội bộ doanh nghiệp và giữa nhiều tổ chức

Liên kết danh tính (identity linking) giúp một hệ thống nhận ra rằng những danh tính đến từ các nguồn xác thực khác nhau có thể thuộc cùng một người hoặc cùng một tài khoản nghiệp vụ. Trong môi trường doanh nghiệp, bài toán xuất hiện khi nhân viên truy cập nhiều ứng dụng nội bộ, công ty có nhiều đơn vị thành viên, hoặc nhân viên của đối tác cần truy cập tài nguyên được chia sẻ giữa các tổ chức.

**Mục tiêu học tập:** phân biệt đăng nhập một lần, liên kết tài khoản và liên kết danh tính liên tổ chức; hiểu ranh giới tin cậy; thiết kế ánh xạ định danh ổn định và quyền truy cập theo từng tổ chức; biết cách triển khai với Spring Security, quản trị vòng đời và tránh lỗ hổng chiếm quyền tài khoản.

## 1. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Có tự động chứng minh hai tài khoản là một người? |
| --- | --- | --- |
| SSO (Single Sign-On) | Một phiên đăng nhập tại nhà cung cấp danh tính cho phép truy cập nhiều ứng dụng đã tích hợp. | Không. |
| Identity federation (liên kết tin cậy danh tính) | Ứng dụng của tổ chức A chấp nhận kết quả xác thực từ IdP của A hoặc một tổ chức B đã được tin cậy. | Không. |
| Account/identity linking | Tạo quan hệ được kiểm chứng giữa định danh bên ngoài và tài khoản nội bộ, hoặc giữa nhiều định danh bên ngoài. | Có, nếu quy trình xác minh và chính sách cho phép. |
| Provisioning | Tạo/cập nhật/khóa tài khoản và tư cách thành viên dựa trên nguồn quản trị nhân sự/danh tính. | Không; đây là quản lý vòng đời. |
| Authorization | Quyết định người đã xác thực được xem/sửa tài nguyên nào, thuộc tenant nào. | Không; phải kiểm tra riêng sau xác thực. |

Ví dụ: Lan dùng tài khoản công ty để vào Portal, CRM và hệ thống hỗ trợ. Cả ba ứng dụng dựa trên cùng một IdP nên Lan có SSO. Nếu Lan còn có danh tính tại công ty đối tác, việc hai phiên cùng có email `lan@example.com` không đủ căn cứ để gộp hai danh tính. Hệ thống phải xác minh cả hai và kiểm tra chính sách chia sẻ dữ liệu.

**Hai phạm vi chính:**

- **Nội bộ doanh nghiệp:** một IdP chung cho nhiều ứng dụng; hoặc nhiều IdP do các đơn vị con vận hành, được điều phối qua một broker. Mục tiêu là trải nghiệm đăng nhập thống nhất và quản lý tập trung.
- **Giữa nhiều tổ chức (B2B/cross-organization):** ứng dụng của tổ chức chủ quản chấp nhận đăng nhập từ IdP đối tác, nhưng tài khoản khách, dữ liệu và quyền vẫn chịu chính sách của tổ chức chủ quản. Sự tin cậy thường giới hạn theo từng tenant, hợp đồng và ứng dụng.

## 2. Các thành phần và ranh giới tin cậy

- **User / principal:** con người hoặc chủ thể truy cập; tên hiển thị, email và phòng ban chỉ là thuộc tính, không phải khóa định danh toàn cục.
- **Identity Provider (IdP):** xác thực người dùng, duy trì danh mục danh tính, phát hành ID token/assertion theo giao thức.
- **Relying Party (RP, với OpenID Connect) / Service Provider (SP, với SAML):** ứng dụng tin cậy kết quả xác thực theo cấu hình đã thỏa thuận.
- **Identity broker:** trung gian kết nối nhiều IdP, chuẩn hóa luồng đăng nhập và phát hành danh tính cho ứng dụng; broker tạo thêm một ranh giới tin cậy.
- **Tenant/organization:** không gian dữ liệu và chính sách riêng. Một người có thể là thành viên nhiều tenant với vai trò khác nhau.
- **Kho ánh xạ:** lưu quan hệ từ định danh ngoài đến người dùng nội bộ và nguồn chứng minh liên kết; cần ràng buộc duy nhất, audit và cơ chế gỡ liên kết.

IdP xác nhận **ai đã đăng nhập tại IdP đó**. Ứng dụng vẫn phải quyết định danh tính ấy tương ứng với tài khoản nội bộ nào, có thuộc tenant được yêu cầu hay không, và được cấp quyền gì. Quyền `admin` của đối tác B không tự trở thành quyền `admin` trong hệ thống A.

Ví dụ tin cậy: công ty A cho phép nhà cung cấp B đăng nhập vào cổng đơn hàng. A có thể tin chữ ký và danh tính do IdP của B phát hành, nhưng B không được tự thêm người vào tenant của A hoặc gán vai trò quản trị của A. Chính sách tiếp nhận và cấp quyền thuộc A.

## 3. Các mô hình triển khai phổ biến

| Mô hình | Luồng tin cậy | Phù hợp khi | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| IdP nội bộ dùng chung | Ứng dụng 1, 2, 3 → IdP doanh nghiệp | Nhiều ứng dụng trong một công ty | Chính sách MFA, phiên đăng nhập, thu hồi quyền và tài khoản |
| Multi-IdP trực tiếp | Ứng dụng → IdP của từng đơn vị/đối tác | Ít đối tác, mỗi bên có IdP ổn định | Cấu hình issuer/client/tenant riêng; số kết nối tăng theo đối tác |
| Hub-and-spoke qua broker | Ứng dụng → broker → các IdP nguồn | Nhiều đơn vị, đối tác, công ty sau sáp nhập | Cấu hình upstream, chuẩn hóa claim, phân biệt issuer gốc và broker |
| Tài khoản khách B2B | Người B → IdP B → ứng dụng A → membership khách tại A | Hợp tác liên tổ chức, cổng đối tác | Lời mời, thời hạn truy cập, chủ dữ liệu, offboarding |
| Hai danh tính liên kết một người | IdP X và IdP Y → cùng user nội bộ sau xác minh | Chuyển công ty, hợp nhất danh tính, nhiều phương thức đăng nhập | Không tự gộp theo email; kiểm toán và khả năng hủy liên kết |

Không có mô hình nào thay thế kiểm soát quyền ở ứng dụng. Trước khi cho người dùng chọn IdP, hệ thống cần xác định tenant đích từ cấu hình phía máy chủ, lời mời hợp lệ hoặc ngữ cảnh đã xác thực; không tin trực tiếp vào một header tenant do trình duyệt tự gửi.

## 4. Giao thức nào phục vụ phần việc nào?

**OpenID Connect (OIDC)** đặt lớp xác thực lên OAuth 2.0. Ứng dụng web thường dùng Authorization Code Flow; Public Client cần PKCE, và nhiều trường hợp confidential client cũng nên bật PKCE. RP nhận ID token để xác thực đăng nhập. Các trường quan trọng gồm `iss` (issuer), `sub` (subject ổn định trong phạm vi issuer), `aud` (client nhận token), thời điểm hết hạn và `nonce` khi có yêu cầu. UserInfo có thể bổ sung thuộc tính nhưng không thay thế việc kiểm tra ID token.

**SAML 2.0** phổ biến với SSO doanh nghiệp lâu đời. IdP gửi assertion cho SP. SP phải xác thực chữ ký, issuer/entityID, `AudienceRestriction`, recipient/destination, điều kiện thời gian và quan hệ với yêu cầu xác thực khi dùng SP-initiated login. Khóa ánh xạ nên dựa trên định danh bền vững do hai bên thỏa thuận, ví dụ cặp `IdP entityID + persistent NameID`; `NameID` dạng email hoặc transient có thể không phù hợp để liên kết lâu dài.

**OAuth 2.0** giải quyết ủy quyền, không tự bảo đảm danh tính người dùng. Access token cấp cho API phải được API xác minh theo issuer/audience/scope và chính sách ứng dụng; không thay ID token bằng access token để đăng nhập. Nhóm OAuth scope không tương đương vai trò tenant nội bộ.

**SCIM 2.0** hỗ trợ đồng bộ người dùng/nhóm và trạng thái active theo vòng đời. SCIM không phải giao thức đăng nhập. Nó bổ sung cho OIDC/SAML để tạo, cập nhật và thu hồi quyền kịp thời.

**LDAP/Kerberos/AD** thường thuộc tầng danh mục và xác thực nội bộ. Chúng có thể là nguồn phía sau IdP; ứng dụng hiện đại thường tích hợp thông qua OIDC/SAML thay vì tự kết nối trực tiếp mọi directory.

## 5. Luồng đăng nhập liên kết với OIDC

Ví dụ người của đối tác B dùng ứng dụng đặt hàng của A:

1. Người dùng chọn tổ chức B theo cổng đăng nhập hoặc lời mời đã được A công nhận. Ứng dụng chọn cấu hình client `partner-b` trên máy chủ.
2. Ứng dụng chuyển hướng trình duyệt tới Authorization Endpoint của IdP B, kèm `state`, redirect URI, và `nonce`/PKCE tùy luồng.
3. IdP B xác thực người dùng (có thể dùng MFA theo chính sách), rồi trả authorization code qua redirect URI đã đăng ký.
4. Ứng dụng đổi code lấy token qua kênh bảo mật; Spring Security/OIDC client kiểm tra thông tin giao thức và ID token theo cấu hình.
5. Ứng dụng trích xuất định danh đã xác thực: tenant đích do máy chủ xác định, `iss` từ token hợp lệ và `sub` từ IdP.
6. Kho ánh xạ tìm local user theo bộ khóa này. Nếu chưa liên kết, chỉ JIT-provision khi chính sách và bằng chứng onboarding cho phép; còn lại hướng người dùng tới luồng lời mời/xác minh.
7. Ứng dụng tải membership, vai trò và hạn truy cập **từ dữ liệu do tổ chức A kiểm soát**, tạo phiên ứng dụng hoặc principal nội bộ. API tiếp tục kiểm tra authorization theo từng tài nguyên.

~~~mermaid
sequenceDiagram
    participant U as Người dùng B
    participant RP as Ứng dụng A (RP)
    participant IDP as IdP của B
    participant DB as Kho ánh xạ và quyền A
    U->>RP: Chọn B / theo lời mời
    RP->>IDP: Yêu cầu OIDC (state, nonce/PKCE)
    IDP-->>RP: Authorization code
    RP->>IDP: Đổi code lấy token
    IDP-->>RP: ID token
    RP->>RP: Xác minh token và tenant đích
    RP->>DB: Tra (tenant, issuer, subject)
    DB-->>RP: User nội bộ + membership
    RP-->>U: Phiên được cấp quyền theo A
~~~

Nếu hệ thống qua broker, `iss` trong token ứng dụng nhận có thể là **issuer của broker**, không phải issuer gốc. Muốn phân biệt upstream IdP phải dùng một claim đã được broker chuẩn hóa, ký và bảo đảm ngữ nghĩa; tuyệt đối không tin chuỗi `upstream_issuer` do trình duyệt tùy ý gửi.

## 6. Thiết kế khóa định danh và mô hình dữ liệu

**Không dùng email, số điện thoại, display name, domain hoặc `preferred_username` làm khóa liên kết bất biến.** Chúng có thể thay đổi, tái sử dụng, trùng giữa tenant hoặc không được xác thực. Ngay cả claim `email_verified` cũng chỉ chứng minh trạng thái xác minh email theo quy tắc IdP, không chứng minh quyền sở hữu tài khoản nội bộ khác.

Một mô hình dữ liệu tham khảo:

| Bảng / đối tượng | Trường thiết yếu | Bất biến cần có |
| --- | --- | --- |
| `local_users` | `user_id`, trạng thái, tên hiển thị | `user_id` nội bộ không phụ thuộc IdP |
| `external_identities` | `tenant_id`, `issuer`, `subject`, `user_id`, trạng thái, thời điểm liên kết, cách xác minh | Khóa duy nhất `(tenant_id, issuer, subject)`; một định danh ngoài không gắn đồng thời với hai local user |
| `organization_memberships` | `user_id`, `organization_id`, vai trò, trạng thái, ngày hết hạn | Mỗi lần truy cập phải kiểm tra membership của tenant đích |
| `trusted_identity_providers` | `organization_id`, `registration_id`, issuer/entityID, trạng thái tin cậy, chính sách nhận người | Không nhận issuer ngoài allowlist gắn với tổ chức |
| `audit_events` | hành động, đối tượng, tác nhân, nguồn xác minh, thời gian | Tra cứu được link/unlink, role change, SCIM deactivate, login failure |

Khóa từ OIDC thường là bộ `(tenant_id, iss, sub)`, trong đó `iss` được lấy từ ID token đã được xác minh theo registration hợp lệ. Nếu mọi tenant dùng cùng một IdP và `sub`, việc thêm `tenant_id` vẫn quan trọng để hạn chế ánh xạ và quyền theo tenant. Nếu hệ thống muốn nhận ra cùng một cá nhân xuyên nhiều tenant, có thể có `person_id` cấp toàn cục, nhưng membership và quyền vẫn tách biệt.

Trên hệ quản trị cơ sở dữ liệu thực, dùng unique constraint cho khóa ngoài; giao dịch khi liên kết; tránh hai yêu cầu đồng thời gắn cùng một định danh vào hai người. Khi IdP thay issuer/subject format, cần quy trình migration có xác thực và audit, không tự gộp hàng loạt theo email.

## 7. Quy trình liên kết hai tài khoản an toàn

Giả sử một người có tài khoản nội bộ A và một danh tính bên B. Liên kết chỉ nên diễn ra qua thao tác rõ ràng:

1. Người dùng đăng nhập tài khoản A đang hoạt động; với thao tác nhạy cảm, yêu cầu xác thực lại gần thời điểm liên kết.
2. Người dùng bấm “Liên kết tổ chức B”; máy chủ khởi tạo luồng OIDC/SAML tới IdP B đã được chấp thuận.
3. Máy chủ xác minh kết quả trả về và đối chiếu `state`/`nonce`, issuer, subject, client, tenant cùng phiên khởi tạo.
4. Máy chủ kiểm tra người dùng có quyền liên kết danh tính B với tài khoản A và danh tính B chưa được liên kết với tài khoản khác. Khi cần, yêu cầu lời mời từ quản trị viên hoặc xác nhận thứ hai.
5. Ghi mapping trong giao dịch có kiểm soát cạnh tranh, lưu thời gian, phương thức chứng minh và tác nhân; phát sự kiện kiểm toán.
6. Hiển thị các danh tính đang liên kết và cách gỡ liên kết; phải giữ ít nhất một phương án đăng nhập/khôi phục hợp lệ để tránh khóa chính mình.

Không triển khai “đăng nhập với B, thấy email giống email A, tự động gộp A và B”. Kẻ tấn công có thể tạo hoặc chiếm một danh tính sở hữu email tái sử dụng ở nguồn khác, dẫn tới **account takeover**. Cũng không tự liên kết chỉ vì IdP B có cùng tên người dùng với A.

**Hủy liên kết:** xác minh lại người dùng, xem các phiên và token liên quan, gỡ mapping an toàn và ghi audit. Nếu người dùng bị vô hiệu hóa ở một IdP, xử lý chính sách tài khoản/membership riêng; mapping còn tồn tại không có nghĩa quyền còn hiệu lực.

## 8. Cấp phát tài khoản và vòng đời giữa tổ chức

Ba lựa chọn cần đánh giá:

- **Pre-provisioning (trước đăng nhập):** quản trị viên A phê duyệt lời mời hoặc đồng bộ SCIM; phù hợp B2B cần kiểm soát chặt. Tài khoản có thể tồn tại trước lần login đầu tiên.
- **Just-in-Time provisioning (JIT):** tạo tài khoản tại lần đăng nhập thành công khi issuer và điều kiện tuyển chọn đã được A phê duyệt. Chỉ OIDC hợp lệ chưa đủ để tự cấp role hoặc tenant.
- **Hybrid:** SCIM/lời mời cấp membership và giới hạn quyền; OIDC/SAML dùng khi đăng nhập và liên kết định danh lần đầu.

Thiết kế đầy đủ vòng đời: thêm nhân viên/đối tác → xác minh và cấp membership → thay đổi bộ phận/vai trò → tạm khóa/nghỉ việc → thu hồi các phiên và quyền → lưu audit theo quy định. Cần thống nhất nguồn nào là authoritative cho `active`, chức danh, nhóm và quyền; xử lý trễ SCIM, webhook thất bại, xóa nhầm, chuyển nhân sự giữa đơn vị. Vô hiệu hóa ở IdP nguồn thường chặn đăng nhập mới, nhưng phiên đã cấp ở ứng dụng hoặc access token cũ có thể tiếp tục tới khi hết hạn/thu hồi theo thiết kế.

Đối với B2B, nên có chủ sở hữu đối tác (sponsor) ở A, ngày hết hạn lời mời, rà soát quyền định kỳ và SLA khóa quyền khi hợp đồng kết thúc. Một IdP của đối tác có quyền xác thực người của **chính đối tác đó**, không có quyền cấp quyền toàn cục trong ứng dụng A.

## 9. Triển khai với Spring Security: các điểm tích hợp

Với Spring Boot 3.x, Java 17+ và ứng dụng web dùng OIDC, khai báo phụ thuộc `spring-boot-starter-security` cùng `spring-boot-starter-oauth2-client`. Mỗi IdP tin cậy có một client registration riêng; Spring Security thực hiện luồng giao thức, còn ứng dụng chịu trách nhiệm ánh xạ và phân quyền nội bộ.

Ví dụ cấu hình **minh họa** cho hai IdP giả định (không dùng giá trị secret minh họa trong môi trường thật):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: portal-corp
            client-secret: REPLACE_FROM_SECRET_MANAGER
            scope: [openid, profile, email]
            authorization-grant-type: authorization_code
          partner-b:
            provider: partner-b
            client-id: portal-partner
            client-secret: REPLACE_FROM_SECRET_MANAGER
            scope: [openid, profile]
            authorization-grant-type: authorization_code
        provider:
          corp:
            issuer-uri: https://idp.corp.example
          partner-b:
            issuer-uri: https://login.partner.example
~~~

Hai đường bắt đầu đăng nhập thường là `/oauth2/authorization/corp` và `/oauth2/authorization/partner-b`, trong khi callback mặc định có dạng `/login/oauth2/code/{registrationId}`. Redirect URI phải đăng ký đúng ở từng IdP; chỉ cung cấp HTTPS và cấu hình secret qua môi trường/secret manager trong triển khai thật. Các tên miền `.example` chỉ là ví dụ.

Một cấu hình bảo vệ ứng dụng web:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FederationSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là file `FederationSecurityConfig.java` trong dự án Spring Boot có các starter nói trên. Cấu hình cho phép OIDC login với các registration đã khai báo; **nó chưa tự liên kết account nội bộ**. Trong ứng dụng thực, tích hợp `OAuth2UserService<OidcUserRequest, OidcUser>` (hoặc xử lý sau đăng nhập có kiểm soát) để ánh xạ claims từ đăng nhập đã xác thực sang `local_user_id` và membership. Cần giữ nguyên validation do thư viện thực hiện, kiểm tra mapping issuer↔registration↔tenant theo cấu hình máy chủ và không dùng email để tự gộp tài khoản.

Ví dụ chuyển một OIDC user **đã được Spring Security xác thực** thành khóa liên kết ở tầng domain:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record FederatedKey(String tenantId, String issuer, String subject) {
    public static FederatedKey from(String targetTenantId, OidcUser user) {
        return new FederatedKey(
            targetTenantId,
            user.getIdToken().getClaimAsString("iss"),
            user.getSubject()
        );
    }
}
~~~

Lưu file `FederatedKey.java`. Tham số `targetTenantId` phải đến từ cấu hình hoặc ngữ cảnh tenant hợp lệ do máy chủ xác minh; không lấy thẳng từ query parameter hoặc header chưa tin cậy. `iss` và `sub` chỉ có ý nghĩa tin cậy **sau khi Spring Security đã xác thực luồng OIDC và token**. Ánh xạ khóa này tới tài khoản và membership nội bộ cần repository/giao dịch/kiểm toán riêng.

Nếu dùng **SAML**, Spring Security cung cấp tích hợp `spring-security-saml2-service-provider` và `saml2Login` với `RelyingPartyRegistration` cho từng IdP; cần quản trị metadata, chứng thư, entityID và Assertion Consumer Service. Nếu API riêng nhận bearer token thì dùng cấu hình **OAuth2 Resource Server** (`spring-boot-starter-oauth2-resource-server`) với validator issuer/audience phù hợp; việc login web và xác minh token API là hai trách nhiệm khác nhau. Với nhiều issuer cho API, cần chiến lược chọn validator đáng tin cậy và áp policy theo tenant, không chỉ giải mã JWT.

## 10. Ví dụ Java 17 chạy độc lập: một người, hai danh tính khác issuer

Đoạn sau minh họa **quy tắc ánh xạ**, không thực hiện OIDC, không kết nối cơ sở dữ liệu và không thay thế bước xác minh danh tính thật. Biến `verified` chỉ mô phỏng kết quả đã xác minh ở tầng bảo mật.

Tạo file `IdentityLinkingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class IdentityLinkingDemo {
    record ExternalIdentity(String tenantId, String issuer, String subject) {}
    record LocalUser(String id) {}

    private static final Map<ExternalIdentity, LocalUser> LINKS = new HashMap<>();

    static void linkAfterVerification(
            ExternalIdentity external, LocalUser user, boolean verified) {
        if (!verified) {
            throw new SecurityException("Identity verification required");
        }
        LocalUser previous = LINKS.putIfAbsent(external, user);
        if (previous != null && !previous.equals(user)) {
            throw new IllegalStateException("External identity already linked");
        }
    }

    static String resolve(ExternalIdentity external) {
        LocalUser user = LINKS.get(external);
        return user == null ? "UNLINKED" : user.id();
    }

    public static void main(String[] args) {
        LocalUser alice = new LocalUser("U-100");
        ExternalIdentity corp = new ExternalIdentity(
            "corp", "https://idp.corp.example", "42");
        ExternalIdentity partner = new ExternalIdentity(
            "partner-b", "https://login.partner.example", "42");

        linkAfterVerification(corp, alice, true);
        System.out.println(resolve(corp));
        System.out.println(resolve(partner));

        linkAfterVerification(partner, alice, true);
        System.out.println(resolve(partner));
        System.out.println(LINKS.size());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac IdentityLinkingDemo.java
java IdentityLinkingDemo
~~~

Kết quả chuẩn:

~~~text
U-100
UNLINKED
U-100
2
~~~

Dù cả hai IdP dùng `subject = "42"`, khóa gồm tenant và issuer khiến chúng không bị nhầm là một. Chỉ sau bước xác minh/link thứ hai, cả hai dẫn tới `U-100`. Trong production, bỏ tham số boolean do caller cung cấp, lấy kết quả xác minh từ phiên và luồng IdP hợp lệ; thay `HashMap` bằng repository có unique constraint và transaction; không giữ mapping nhạy cảm thuần trong bộ nhớ của một instance.

## 11. Các lỗ hổng thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghép user theo email/username | Chiếm tài khoản, nhầm người sau đổi/tái sử dụng email | Dùng khóa ổn định issuer + subject + tenant; liên kết có chứng minh |
| Tin `tenant_id` hoặc `role` do client gửi | Truy cập chéo tenant, leo thang đặc quyền | Dùng trusted mapping và quyền server-side |
| Nhận token nhưng không kiểm tra issuer/audience/chữ ký/thời hạn | Token của ứng dụng/IdP khác được chấp nhận | Validator chuẩn, allowlist issuer và audience, quản trị JWKS |
| Bỏ `state`/`nonce`, callback không ràng buộc phiên | Login CSRF, replay, trộn phiên | Dùng OIDC library đúng cách, kiểm tra state/nonce và PKCE |
| Trộn role nguồn với role ứng dụng | Đối tác tự mang quyền cao sang ứng dụng | Mapping role riêng theo tenant, mặc định quyền tối thiểu |
| JIT cấp tài khoản cho mọi identity hợp lệ | Bất kỳ người dùng IdP được tin đều vào ứng dụng | Whitelist, invitation, chính sách enrollment và phê duyệt |
| Không đồng bộ offboarding | Tài khoản/phiên khách tồn tại sau hết hợp tác | SCIM/deprovisioning, session revocation, expiry và audit |
| Không xử lý trùng mapping cạnh tranh | Một external identity gắn nhiều local user | Unique constraint, transaction, idempotent link operation |
| Quá tin broker hoặc IdP bị xâm nhập | Identity giả được hệ thống chấp nhận | Hạn chế phạm vi trust, MFA, monitor, kiểm toán, kế hoạch cắt liên kết |

Với SAML, bổ sung kiểm tra chữ ký assertion/response đúng yêu cầu, issuer/entityID, recipient, audience, `InResponseTo`, thời hạn và chống replay; không chỉ parse XML rồi tin các thuộc tính. Với OIDC, dùng thư viện đã kiểm thử để xử lý token và callback; không tự viết bộ xác minh JWT hoặc tự bỏ qua chứng thư khi kết nối IdP.

## 12. Ví dụ áp dụng thực tế

**Tình huống nội bộ:** tập đoàn có nhân sự ở hai đơn vị A1/A2, một Portal và nhiều dịch vụ. Có thể dùng IdP tập đoàn hoặc broker nối IdP từng đơn vị. Ứng dụng ánh xạ `(tenant, issuer, sub)` tới `local_user_id`, từ đó cấp quyền Portal theo đơn vị. Khi nhân sự chuyển A1 sang A2, xử lý membership có kiểm soát; không suy diễn rằng SSO sang ứng dụng A2 đồng nghĩa có quyền xem dữ liệu A2.

**Tình huống liên tổ chức:** A cung cấp cổng B2B cho nhà cung cấp B và C. Mỗi đối tác đăng nhập tại IdP riêng. A cấu hình issuer/registration theo đối tác, yêu cầu lời mời và thời hạn khách, ghi mapping, rồi cấp quyền `ORDER_VIEWER` hoặc `ORDER_EDITOR` **theo từng hợp đồng/tenant**. Nhân viên B dù có `admin` tại B cũng không thể tự xem đơn của C. Khi hợp đồng B kết thúc, A vô hiệu hóa membership và các phiên liên quan, ngay cả khi danh tính ở IdP B vẫn tồn tại.

**Tình huống hợp nhất công ty:** sau sáp nhập, cùng một nhân viên có account ở IdP cũ và mới. Bộ khóa bền vững giữ hai danh tính tách biệt; quản trị viên thực hiện migration có xác minh và audit, rồi liên kết chúng với một user nội bộ nếu chính sách cho phép. Không dùng email để hợp nhất tự động hàng loạt.

## 13. Checklist thiết kế, vận hành và kiểm thử

1. **Trust:** tài liệu hóa mỗi cặp tổ chức↔issuer, endpoint, client registration, chứng thư/JWKS, thuật toán, hợp đồng và người sở hữu; có quy trình xoay khóa/cắt trust.
2. **Identity:** khóa `(tenant, issuer, subject)` duy nhất; lưu lịch sử liên kết; quy trình link/unlink dựa trên hai bằng chứng xác thực và chính sách được phê duyệt.
3. **Tenant authorization:** user có thể thuộc nhiều tổ chức nhưng truy cập mỗi lần chỉ theo membership, vai trò, tài nguyên và tenant đích hợp lệ.
4. **Lifecycle:** xác định nguồn nhân sự authoritative, lời mời/SCIM/JIT, kích hoạt, tạm khóa, chuyển bộ phận, xóa quyền, hết hạn khách, thu hồi phiên.
5. **Bảo mật:** MFA/step-up khi link hoặc vào dữ liệu nhạy cảm; HTTPS, secret manager, redirect URI allowlist, state/nonce/PKCE, audit log không rò token/secret.
6. **Vận hành:** giám sát login/claim mismatch, thay đổi issuer/JWKS, lỗi đồng bộ SCIM, liên kết trùng, anomalous sign-in; có đường hỗ trợ khi IdP đối tác ngừng hoạt động.
7. **Kiểm thử bắt buộc:** cùng `sub` nhưng khác `iss` không được auto-merge; cùng email khác issuer không auto-link; user B không xem dữ liệu C; IdP lạ hoặc token sai audience bị từ chối; tài khoản nghỉ việc hết quyền; hai yêu cầu link đồng thời không tạo mapping trái phép; quyền bị thu hồi không tiếp tục dùng qua phiên cũ vượt giới hạn đã định.
8. **Kiểm thử trải nghiệm:** người dùng biết mình đang dùng tổ chức nào, thấy thông tin danh tính đã liên kết, hiểu lý do bị từ chối và có đường khôi phục an toàn khi mất một IdP.

**Nguyên tắc cốt lõi:** federation cho phép tin vào **kết quả xác thực có nguồn gốc**, identity linking xác lập **quan hệ giữa các danh tính sau xác minh**, còn authorization quyết định **quyền trong tenant và tài nguyên cụ thể**. Tách ba lớp này là điều kiện để mở rộng SSO nội bộ sang cộng tác nhiều tổ chức mà vẫn kiểm soát được tài khoản và dữ liệu.