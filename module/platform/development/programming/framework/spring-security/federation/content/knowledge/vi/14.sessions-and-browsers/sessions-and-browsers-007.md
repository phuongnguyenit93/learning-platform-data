# Thay đổi quyền hoặc khóa tài khoản khi phiên ứng dụng SAML 2.0 vẫn còn hiệu lực

## 1. Bài toán thực tế: IdP đã khóa nhưng ứng dụng vẫn cho truy cập?

Giả sử nhân viên đăng nhập cổng Spring Boot thông qua SAML 2.0 lúc **09:00**. IdP xác minh người dùng và gửi một `SAMLResponse` có chữ ký hợp lệ. Spring Security tạo một `Authentication`, lưu vào `SecurityContext`, rồi duy trì phiên HTTP của **Service Provider (SP)**. Đến **10:00**, quản trị viên thay quyền từ `PAYMENT_APPROVE` thành chỉ xem, hoặc khóa tài khoản ở hệ thống danh tính. Lúc **10:01**, trình duyệt vẫn còn cookie phiên SP và gửi yêu cầu phê duyệt thanh toán.

Câu hỏi quan trọng: **Spring Security có tự biết tài khoản đã bị khóa hoặc quyền đã bị thu hồi không?** Trong mô hình session thông thường, **không thể mặc định như vậy**. Spring Security phục hồi `Authentication` đã lưu; các `GrantedAuthority` được tạo lúc đăng nhập có thể vẫn phản ánh ảnh chụp quyền cũ. SAML Web Browser SSO **không liên tục hỏi IdP** về trạng thái tài khoản khi mỗi request đến SP.

Bài học thuộc **Spring Security - federation → Phiên và trình duyệt**, tập trung vào thay đổi quyền và khóa tài khoản **trong khi session ứng dụng vẫn tồn tại**; không nhầm với hành vi của một lần SAML login mới.

### Sau bài học, bạn có thể

1. Phân biệt phiên **IdP**, phiên **SP**, `SAML Assertion`, `SecurityContext`, `Authentication` và dữ liệu phân quyền nghiệp vụ.
2. Giải thích vì sao khóa tài khoản tại IdP hoặc đổi group/role **không tự cập nhật session SP**.
3. Phân biệt **authentication** (ai đang truy cập) và **authorization** (được phép làm gì ngay lúc này).
4. Áp dụng ba lớp bảo vệ: **kiểm tra trạng thái/quyền hiện hành**, **thu hồi session có chủ đích**, **thời hạn session/reauthentication**.
5. Hiểu khi nào cần Spring Session + indexed session repository, Spring Security `SessionRegistry` và quyền hạn của mỗi giải pháp.
6. Thiết kế xử lý event từ hệ thống IAM/SCIM/HR/IdP theo thứ tự phiên bản, chống replay, bỏ sót và nhất quán nhiều node.
7. Tạo `AuthorizationManager<RequestAuthorizationContext>` dùng trạng thái hiện hành thay vì chỉ dựa trên authorities cũ.
8. Biết cách kiểm thử khóa tài khoản, thu hồi quyền, nhiều thiết bị, concurrent requests, WebSocket và hành vi SSO lại sau khi logout.
9. Không hạ an toàn bằng cách tắt chữ ký SAML, bỏ CSRF, chấp nhận URL logout tùy ý hoặc coi client UI là nơi quyết định quyền.

**Môi trường ví dụ:** Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet/MVC; phần ghi chú áp dụng bản 7.x khi API tương ứng. Tên miền `app.example.org`, `idp.example.org` và account giả trong bài chỉ là ví dụ học tập.

## 2. Cơ chế gốc: sau một lần SAML login, SP giữ phiên riêng

Sơ đồ một phiên thông thường:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as SAML IdP
    participant D as Application identity and permissions
    B->>SP: GET /payments
    SP-->>B: Chuyển sang IdP
    B->>I: SAML AuthnRequest
    I-->>B: Đăng nhập thành công, SAMLResponse
    B->>SP: POST SAMLResponse tại ACS
    SP->>SP: Verify signature, issuer, audience, time, InResponseTo
    SP->>SP: Tạo Saml2Authentication + SecurityContext
    SP-->>B: Session cookie, truy cập /payments
    B->>SP: GET /payments với cookie SP
    SP->>SP: Phục hồi Authentication từ SecurityContextRepository
    SP-->>B: Trang /payments nếu authorization cho phép
    Note over I,SP: Không mặc định hỏi IdP ở mỗi GET/POST
    D-->>D: Lúc 10:00 quyền hoặc trạng thái user thay đổi
    B->>SP: POST /payments/approve với cookie cũ
    Note over SP,D: Cần cơ chế kiểm tra/quản lý thay đổi riêng
~~~

### Những đối tượng không tương đương

| Đối tượng | Dữ liệu tiêu biểu | Vòng đời và ý nghĩa |
| --- | --- | --- |
| **IdP session** | Cookie/session tại domain IdP | Cho IdP nhớ người dùng; SP không sở hữu và không tự xóa nó |
| **SAMLResponse/Assertion** | NameID, AttributeStatement, AuthnStatement, Conditions, chữ ký | Bằng chứng đăng nhập được SP kiểm tra tại callback; **không phải stream cập nhật quyền liên tục** |
| **Saml2Authentication** | Principal, authorities, serialized response theo API framework | Kết quả xác thực do Spring tạo sau khi chấp nhận Assertion |
| **SecurityContext** | `Authentication` hiện hành | Thường được phục hồi từ session theo `SecurityContextRepository` |
| **HttpSession** | ID session, context/các state ứng dụng | Có thể tồn tại sau khi IdP khóa tài khoản; timeout phụ thuộc SP |
| **App account/permission store** | `enabled/locked`, role, tenant, quyền trên tài nguyên, phiên bản policy | **Nguồn quyền hiện tại** do ứng dụng/IAM được chọn làm thẩm quyền |
| **Browser cookie SP** | Session ID hoặc cookie định danh theo cấu hình | Chỉ giúp tham chiếu phiên; cookie còn hiệu lực không chứng minh quyền hiện tại |
| **Access token khác** | JWT/OAuth token cho API khác | Có vòng đời và cơ chế revoke riêng, không tự bị hủy vì SAML SLO |

**Điểm chính:** với SAML, lúc user xác thực ở IdP, SP có thể lấy một tập attributes/groups/authorities và lưu vào phiên. Đến khi các attributes đó thay đổi ở IdP, SP **không mặc định nhận một event** hay tự so SAML Response cũ với dữ liệu mới. Spring Security chỉ thực hiện những kiểm tra mà ứng dụng đã cấu hình.

## 3. Hai sự kiện giống nhau trên UI nhưng khác về kỹ thuật

### 3.1 Thu hồi hoặc thay quyền

Ví dụ nhân viên bị gỡ quyền `FINANCE_APPROVE` nhưng tài khoản vẫn được phép đăng nhập. Nếu app chỉ dùng:

~~~java
.requestMatchers("/finance/approve/**").hasAuthority("FINANCE_APPROVE")
~~~

và `Authentication.getAuthorities()` đã có giá trị đó từ 09:00, yêu cầu 10:01 có thể **vẫn được cho phép**. `hasAuthority` kiểm tra authorities của `Authentication` tại thời điểm request; nó **không phải phép truy vấn quyền hiện hành ở IdP**.

### 3.2 Khóa/vô hiệu hóa tài khoản

Ví dụ đội IAM đặt `locked=true` hoặc `enabled=false` tại IdP. Điều này thường ảnh hưởng **lần xác thực tiếp theo ở IdP**, nhưng **không bảo đảm** SP đang giữ phiên tự kết thúc ngay. Nếu SP không có dữ liệu trạng thái local hoặc kênh cập nhật tin cậy, người dùng vẫn có thể sử dụng phiên SP đến khi logout, timeout hoặc SP có kiểm soát khác.

Một hệ thống tốt phải quyết định rõ:
- Khóa tài khoản tại **IdP** có tự kéo theo cấm truy cập **SP đang active** không?
- Nguồn nào là **authoritative** cho từng quyền ứng dụng?
- Độ trễ thu hồi tối đa được phép là bao nhiêu giây/phút?
- Có phải ngắt **mọi session** hay chỉ từ chối những hành động nhạy cảm?
- Ai phát **event**, ai xử lý thất bại và kiểm soát version?
- Có cần thu hồi **token, WebSocket, job nền và phiên trên thiết bị khác** ngoài HttpSession không?

Không có một API SAML 2.0 chung nào bảo đảm mọi app tự cập nhật trạng thái quyền hiện hành mà không có thiết kế riêng.

## 4. Phân biệt ảnh chụp quyền và quyền hiện hành

| Loại kiểm tra | Nguồn dữ liệu | Thuận lợi | Rủi ro nếu dùng riêng |
| --- | --- | --- | --- |
| **Authorities ở Authentication** | Được cấp khi SP xác thực/mapper ánh xạ SAML attributes | Nhanh, tích hợp `hasAuthority`/`@PreAuthorize` | Có thể **stale** sau thay quyền |
| **Local account DB hiện hành** | DB/store của ứng dụng | Quyền theo nghiệp vụ, truy vấn runtime, có thể audit | Cần quản lý đồng bộ với IAM và độ tin cậy DB |
| **Central authorization service/policy engine** | PDP/OPA/IAM authorization API | Quyết định tập trung, có thể nhận policy mới | Độ trễ, availability, cache và fail-closed cần thiết kế |
| **Event-driven local snapshot** | Event IAM/HR/IdP/SCIM cập nhật cache/DB | Độ trễ thấp, giảm request về IdP | Có thể mất event, reorder, replay, stale cache |
| **Session invalidation** | Session store/registry | Ép lần truy cập sau không còn SP authentication cũ | Có khoảng trễ, không tự khóa IdP, và không thay authorization |
| **Reauthentication** | SAML flow mới tới IdP | Có thể nhận trạng thái IdP ở lần login mới | Không cập nhật mọi phiên/permission nếu user đã có SP session; không đủ một mình |

**Quy tắc:** đối với hành động có rủi ro cao như chuyển tiền, cấp quyền, truy xuất bí mật hoặc xuất dữ liệu nhạy cảm, hãy kiểm tra **account state và quyền hiện hành sát thời điểm hành động**. Chỉ dựa vào `ROLE_ADMIN` đã lưu trong session từ trước có thể không đáp ứng yêu cầu thu hồi quyền khẩn cấp.

## 5. Kết quả truy cập khi user bị khóa sau khi login

Một bảng chính sách điển hình:

| Trạng thái hiện hành | Session SP | Hành động | Kết quả an toàn |
| --- | --- | --- | --- |
| Enabled, đủ quyền | Còn | Xem dữ liệu được phép | Allow |
| Enabled, quyền vừa bị gỡ | Còn, chứa role cũ | Phê duyệt thanh toán | **Deny** theo quyền mới |
| Locked/disabled | Còn | Bất kỳ tài nguyên bảo vệ | **Deny**, tùy policy còn chủ động revoke session |
| Không tìm thấy account | Còn | Tài nguyên bảo vệ | **Deny** nếu account store là nguồn kiểm soát |
| Store trạng thái tạm không truy cập được | Còn | Hành động rủi ro cao | **Fail closed**; không tự tin authorities snapshot cũ |
| Session SP đã bị xóa | Cookie cũ còn | Truy cập route bảo vệ | Không còn Authentication; thường quay login/challenge |
| IdP session vẫn còn, SP session đã bị xóa | Trình duyệt mở lại app | Bắt đầu SSO mới | IdP có thể tự đăng nhập lại; **SP phải kiểm tra account local hiện hành** |
| User khóa ở SP nhưng IdP chưa khóa | IdP vẫn có session | SP nhận SAMLResponse hợp lệ mới | Không cấp quyền truy cập nếu chính sách SP cho rằng account bị khóa |

**Nên quyết định status/UX rõ ràng:** user có Authentication nhưng không đủ quyền có thể nhận 403; session bị thu hồi có thể được dẫn đến login; business exception có thể hiển thị tài khoản bị vô hiệu hóa bằng thông báo chung. Đừng phụ thuộc một status HTTP cố định cho mọi chain và entry point.

## 6. Vì sao Spring không cập nhật GrantedAuthority tự động?

Ở Servlet stack, Spring Security dùng `SecurityContextHolder` cho request đang thực thi và `SecurityContextRepository` để phục hồi/lưu `SecurityContext` giữa các request. Nếu dùng session-based login, Authentication trong session có thể chứa danh sách `GrantedAuthority` được ánh xạ khi đăng nhập.

Sau lần SAML login:
1. `Saml2WebSsoAuthenticationFilter` nhận SAMLResponse tại ACS.
2. Provider/OpenSAML kiểm tra chữ ký, issuer, audience, conditions, subject và các ràng buộc liên quan.
3. Spring tạo `Saml2Authentication` và `Saml2AuthenticatedPrincipal`, có thể ánh xạ attributes sang authorities.
4. SecurityContext được lưu để dùng trên các request tiếp theo theo cấu hình.
5. Khi request sau đến, `hasRole/hasAuthority` lấy authorities trên Authentication đang có.

Không có mặc định “trước mỗi `hasAuthority`, hỏi IdP xem user còn trong group không”. Làm điều đó sẽ biến SP phụ thuộc request network đến IdP và nằm ngoài contract SAML browser SSO thông thường.

Một attribute như `group=finance-admin` có thể là sự thật ở **thời điểm assertion được phát**, nhưng không đại diện một cách tự động cho **hiện tại**. Thời hạn `Conditions@NotOnOrAfter` của assertion được kiểm tra tại login, không đồng nghĩa việc session SP phải tự bị hủy đúng thời điểm đó trừ khi ứng dụng đã áp dụng chính sách cụ thể.

## 7. Ba lớp kiểm soát nên phối hợp

### Lớp A — Kiểm tra trạng thái/quyền hiện hành khi nhận request

Trước khi xử lý các route bảo vệ hoặc phương thức nghiệp vụ nhạy cảm, kiểm tra:
- Account còn **enabled**, không bị **locked** hoặc deleted;
- Không bị cách ly theo tenant/organization hoặc employment state;
- Quyền hành động còn trong **nguồn quyền hiện hành**, không chỉ từ snapshot Authentication;
- Đối tượng tài nguyên (đơn hàng, tài khoản ngân hàng, tài liệu) còn được user truy cập theo policy đối tượng;
- Nếu cần, account authorization version của phiên không thấp hơn version đã áp dụng.

### Lớp B — Thu hồi phiên SP khi nhận sự kiện đáng tin

Khi IAM thông báo user bị khóa hoặc quyền bị thu hồi, chủ động:
- Xóa/invalidate HTTP sessions tương ứng qua Spring Session indexed repository hoặc cơ chế session registry;
- Xóa các cache authorizations/permissions liên quan;
- Thu hồi các app tokens/refresh tokens nếu có trong phạm vi ứng dụng;
- Ghi audit và đẩy sự kiện cho các node/worker theo hợp đồng;
- Đánh dấu account disabled trước khi hủy session, để lần SSO lại **không mở quyền trở lại**.

### Lớp C — Giới hạn vòng đời và buộc xác thực mới khi cần

Cấu hình:
- Session idle timeout và absolute timeout (nếu requirement cần);
- SecurityContext session fixation protection và CSRF;
- Cơ chế **reauthentication/step-up** cho hành động nhạy cảm;
- Thời hạn cache quyền (TTL hoặc version) và chính sách fail-closed;
- Giám sát session còn dùng sau thời điểm revocation.

**Không coi lớp C thay được A/B.** Nếu account lock cần có hiệu lực trong 10 giây thì timeout session 30 phút không đáp ứng. Nếu revoke event bị mất, lớp A vẫn có thể chặn.

## 8. Ví dụ Spring Security: kiểm tra trạng thái live bằng AuthorizationManager

Ví dụ sau cho thấy **thay quyền trong kho trạng thái ứng dụng có hiệu lực ở request tiếp theo**, dù Authentication SAML cũ vẫn chứa role từng được cấp. Nó dùng một **in-memory account store trong lab** để minh họa. Trong production cần thay store bằng nguồn tin cậy như database/policy engine và đồng bộ IAM đúng quy trình.

### 8.1 Mô hình AccountPolicy

Tệp `src/main/java/com/example/federation/AccountPolicy.java`:

~~~java
package com.example.federation;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;

@Component
public class AccountPolicy {

    public record AccountState(boolean enabled,
                               Set<String> permissions,
                               long version) {
    }

    private final ConcurrentMap<String, AccountState> states =
            new ConcurrentHashMap<>();

    private static String key(String registrationId, String subject) {
        return registrationId + "\u0000" + subject;
    }

    public boolean allowed(Authentication authentication, String permission) {
        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal()
                        instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }

        String principalKey =
                key(principal.getRelyingPartyRegistrationId(), principal.getName());
        AccountState current = states.get(principalKey);

        // Unknown/disabled -> deny, irrespective of stale session roles.
        return current != null && current.enabled()
                && current.permissions().contains(permission);
    }

    // Only a trusted IAM/provisioning component should invoke this method.
    public void applyTrustedChange(String registrationId,
                                   String subject,
                                   boolean enabled,
                                   Set<String> permissions,
                                   long version) {
        String principalKey = key(registrationId, subject);
        states.compute(principalKey, (ignored, previous) -> {
            if (previous != null && version <= previous.version()) {
                return previous; // ignore duplicate or out-of-order changes
            }
            return new AccountState(enabled, Set.copyOf(permissions), version);
        });
    }
}
~~~

**Đây là Java/Spring code trong một project**, không phải chương trình độc lập chạy chỉ bằng `javac AccountPolicy.java`. Nó cần Spring Security SAML2 dependency và một principal có registrationId. Không có stdout cố định. Các thuộc tính `getRelyingPartyRegistrationId()` và `getName()` được dùng để **không gộp nhầm người dùng từ nhiều IdP** chỉ vì trùng một tên hiển thị.

**Các giới hạn và nguyên tắc vận hành:**

- `ConcurrentHashMap` chỉ tồn tại trong JVM của một node, **không tự đồng bộ đa replica**, mất dữ liệu khi restart. Đưa authoritative state vào database hoặc cache có chính sách sync và TTL.
- `applyTrustedChange` không phải HTTP endpoint công khai; chỉ gọi từ thành phần IAM/provisioning đã xác minh source, authorization và event integrity.
- `version` tăng theo **một thứ tự do nguồn dữ liệu kiểm soát cho từng account**, không lấy timestamp client tự khai. Event mới có version thấp hơn bị bỏ, tránh thay trạng thái mới bằng dữ liệu cũ.
- Đây là demo dùng `registrationId + NameID` làm khóa. Một số IdP dùng **transient NameID** có thể thay đổi giữa lần login, nên production phải ánh xạ sang **immutable external subject** đã được xác minh và đúng tenant; không dùng email tùy ý làm khóa toàn cục.
- Nếu một account chưa được tạo trong store thì **deny**. Trong lab phải seed account qua luồng đáng tin trước khi truy cập.
- Code bảo vệ route nào dùng `allowed`; không ngăn một endpoint riêng vô tình chỉ kiểm tra `hasRole` nếu ứng dụng không áp chính sách thống nhất.

### 8.2 Gắn policy vào SecurityFilterChain

Tệp `src/main/java/com/example/federation/LiveAuthorizationConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LiveAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            AccountPolicy accounts)
            throws Exception {

        return http
                .authorizeHttpRequests(authz -> authz
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .requestMatchers(HttpMethod.POST, "/payments/**")
                        .access((authentication, context) ->
                                new AuthorizationDecision(accounts.allowed(
                                        authentication.get(), "PAYMENT_APPROVE")))
                        .anyRequest()
                        .access((authentication, context) ->
                                new AuthorizationDecision(accounts.allowed(
                                        authentication.get(), "APP_ACCESS"))))
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**Ý nghĩa:**
- `AuthorizationFilter` đánh giá các HTTP request dựa trên `AuthorizationManager<RequestAuthorizationContext>`.
- `accounts.allowed(... )` kiểm tra **trạng thái account hiện hành trong store**, không dựa riêng trên `Authentication.getAuthorities()`.
- Với `POST /payments/**`, yêu cầu permission hiện hành `PAYMENT_APPROVE`; các route khác yêu cầu `APP_ACCESS`.
- Khi IAM bỏ permission đó khỏi store, request tiếp theo bị từ chối dù Authentication cũ vẫn có `FINANCE_ADMIN`.
- `permitAll` chỉ dành cho các endpoint thực sự công khai; endpoint login/ACS và cơ chế SAML filter cần được giữ hoạt động theo Spring Security.
- Request matcher `POST /payments/**` chỉ minh họa, **không thay authorization ở tầng nghiệp vụ**: route GET xem lịch sử, PUT tạo/sửa, hoặc gọi method trực tiếp từ job/GraphQL vẫn phải có kiểm tra tương ứng.
- Không có policy để tự xử lý dữ liệu từ IdP khi account chưa được provisioning. Nếu IdP login thành công nhưng app chưa biết account, **deny** là hành vi có chủ đích.
- Application phải có Spring Boot main, `RelyingPartyRegistrationRepository` thật và Spring SAML dependency; không tự có SSO từ hai class này.

### 8.3 Phân quyền ở mức phương thức

Bảo vệ HTTP route chỉ là một lớp. Service có thể được gọi bởi nhiều adapter (REST, GraphQL, message consumer, scheduled job). Với Spring-managed bean, có thể thêm method security:

~~~java
package com.example.federation;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentApprovalService {

    @PreAuthorize("@accountPolicy.allowed(authentication, 'PAYMENT_APPROVE')")
    public void approvePayment(long paymentId) {
        // Business service implementation goes here.
    }
}
~~~

Đây là **mảnh code chỉ minh họa annotation**, method body thực tế cần domain validation/transaction. Phải bật **`@EnableMethodSecurity`** trên Spring configuration:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

- `@PreAuthorize` được đánh giá theo `Authentication` hiện tại và bean `accountPolicy` do Spring đăng ký.
- Phương thức nhạy cảm vẫn cần kiểm tra quyền đối với **đối tượng cụ thể**, ví dụ tài khoản/đơn hàng/tenant, chứ không chỉ permission tổng quát.
- Nếu service được gọi qua **self-invocation** trong cùng bean, cơ chế Spring proxy method security có thể không áp dụng theo cách mong đợi; cần thiết kế boundary.
- `@EnableMethodSecurity` không được tự động bật chỉ vì có Spring Boot Starter Security.
- Với background task không có HTTP Authentication, phải dùng **service identity và policy riêng**, không giả lập quyền của user từ một SecurityContext thread-local đã cũ.

## 9. Điểm cần cải tiến khi đưa ví dụ thành production

Code lab ở trên chỉ minh họa quyết định; sản phẩm phải thêm:

| Vấn đề | Tại sao quan trọng | Cách thiết kế |
| --- | --- | --- |
| **Nguồn authoritative** | App không thể tự biết mọi IdP thay đổi | Đồng bộ IAM/HR/SCIM hoặc query account DB đã xác minh |
| **Immutable subject** | NameID có thể transient, email đổi, user name có thể tái sử dụng | Map IdP entity/tenant + stable external ID sang account nội bộ |
| **Multi-node consistency** | ConcurrentMap không chia sẻ | DB/Redis/policy engine, event fan-out/version tracking |
| **Quyền ở resource-level** | Permission `APP_ACCESS` chưa quyết định user có sở hữu payment hay không | Kiểm tra ownership/tenant/object ACL trong transaction |
| **In-flight requests** | Request bắt đầu trước event có thể hoàn tất sau khóa | Kiểm tra quyền **gần bước commit**, cân nhắc concurrency/locking |
| **Stale cache** | Cache permission không cập nhật kịp | TTL ngắn theo risk, event invalidation, version hoặc no-cache cho hành động nhạy cảm |
| **Availability** | IAM/DB down có thể làm mọi request fail | Chọn fail-closed cho hành động nguy hiểm, circuit breaker, UX rõ |
| **Session revocation** | AuthN cũ có thể vẫn là authenticated | Delete sessions/expire, audit, nhưng luôn có live gate |
| **WebSocket/API tokens** | Không đi qua cùng HTTP AuthorizationFilter cho mọi message | Thêm message authorization/revocation/token policy riêng |
| **Observability** | User báo “vẫn xem được” cần bằng chứng | Log event/account-version/session-id hash, deny metrics và replay-safe audit |

**Điểm chốt:** không cố “sửa” danh sách authorities bên trong tất cả `SecurityContext` đang sống theo cách ad hoc mà không có transactional/invalidation strategy. Đó là object trong những phiên khác nhau, có thể được serialize, nằm ở nhiều node; việc cập nhật một object trong node này không bảo đảm cập nhật node khác. Kiểm tra quyết định dựa trên nguồn quyền hiện hành thường dễ lý giải và an toàn hơn.

## 10. Thu hồi session bằng Spring Session

Nếu muốn khóa account khiến **những session SP hiện có không thể tiếp tục được sử dụng**, cần một session repository có khả năng tìm đúng session của user. Với Spring Session + Redis **indexed repository** hoặc backend tương đương, có interface:

~~~java
org.springframework.session.FindByIndexNameSessionRepository
~~~

Nó cung cấp `findByPrincipalName(principalName)` và `deleteById(sessionId)`. Lưu ý **không phải mọi SessionRepository đều có index này**; trong Redis cần cấu hình repo phù hợp (tùy version/module, ví dụ Spring Session Data Redis indexed sessions).

### 10.1 Lớp Java minh họa thu hồi session có index

Tệp `src/main/java/com/example/federation/AccountSessionRevoker.java`:

~~~java
package com.example.federation;

import java.util.ArrayList;
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeByIndexedPrincipal(String principalName) {
        Map<String, ? extends Session> matching =
                sessions.findByPrincipalName(principalName);

        var sessionIds = new ArrayList<>(matching.keySet());
        for (String sessionId : sessionIds) {
            sessions.deleteById(sessionId);
        }
        return sessionIds.size();
    }
}
~~~

**Đây là thành phần Spring trong ứng dụng có Spring Session được cấu hình**, không phải Java chạy độc lập. Cần có **bean indexed SessionRepository**; nếu không, dependency injection sẽ thất bại. Trong hệ nhiều IdP, `principalName` có thể không duy nhất giữa tenants/IdP. **Chỉ dùng cách này khi chính sách định danh principal trong Spring Session bảo đảm globally unique đúng account cần revoke.** Nếu không, xây index riêng từ key `(tenant, issuer, immutableSubject)` → tập session IDs, kiểm chứng lại ownership trước khi delete. Không gọi API với email lấy từ form quản trị chưa được xác thực và cho phép xóa session tùy ý.

Giải thích:
1. `findByPrincipalName` tra session được index theo principal name mà repository lưu. Có thể dùng để quản lý phiên theo account trong các triển khai phù hợp.
2. `deleteById` xóa session trong store: request kế tiếp dùng cookie cũ sẽ không khôi phục được cùng SecurityContext theo session đó.
3. Giữa lúc tìm ID và lúc delete có thể có session mới được tạo, hoặc request đang xử lý đã load context; giải pháp **không mang tính atomic toàn hệ thống**. **Live account gate** vẫn cần thiết.
4. Điều kiện “account bị khóa” phải được ghi vào nguồn authoritative **trước** khi bắt đầu revoke. Một SAML login mới sau đó không được qua gate chỉ vì IdP vẫn có session.
5. Không lấy số session xóa như bằng chứng mọi phiên trên các ứng dụng khác hoặc tất cả thiết bị đã logout. Đó chỉ là các session nhìn thấy trong **repository này** tại thời điểm tra.
6. Nếu dùng Spring Session WebSocket support, xóa/expire session có thể kích hoạt cleanup liên quan qua event; tuy vậy các kết nối/worker custom vẫn cần test và xử lý riêng.

### 10.2 Cảnh báo về session principal index

Spring Session xây dựng index theo principal được nhận diện bởi integration, thường từ SecurityContext hoặc `Principal#getName`. Với multi-tenant SAML, hai IdP có thể cùng trả `name=alice`, hoặc IdP có thể đổi NameID format. Nếu index chỉ dùng “alice”, `revokeByIndexedPrincipal("alice")` có nguy cơ xóa session của nhiều account không liên quan. Production nên dùng **stable global principal naming** hoặc bảng mapping phiên riêng, đã kiểm chứng issuer/tenant/account ID và authorization của caller.

Trong mọi trường hợp, thao tác revoke phải:
- Chỉ do hệ thống IAM/admin có quyền thực hiện;
- Được audit (ai, tại sao, account nào, event version nào);
- Có rate limit và idempotency;
- Không trả session IDs thật cho client công khai;
- Không ghi cookie hoặc raw SecurityContext vào log.

## 11. SessionRegistry trong Spring Security có thể hỗ trợ gì?

Ngoài Spring Session, Spring Security có `SessionRegistry` và `SessionInformation` phục vụ quản lý phiên/concurrent sessions. Có thể đánh dấu session **expired**:

~~~java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
~~~

Đây chỉ là **snippet**, cần import, một bean `SessionRegistry` đã cấu hình và principal object phù hợp; không thể chạy độc lập. Trong cơ chế concurrent session control, `ConcurrentSessionFilter` có thể phát hiện expired session khi request tiếp theo đi qua filter và thực hiện logout theo cấu hình.

**Khác biệt quan trọng:**

| Cơ chế | Tác động | Điều kiện/giới hạn |
| --- | --- | --- |
| `SessionInformation.expireNow()` | Đánh dấu phiên hết hiệu lực trong registry | Phụ thuộc filter/config và việc registry nhìn thấy session; không tự chắc xóa ngay cookie trên mọi node |
| `Spring Session deleteById` | Xóa record trong session store | Cần indexed repository và mapping đúng account; request đang chạy có thể tiếp tục |
| `HttpSession.invalidate()` | Hủy session đang gắn với một request/context | Không mặc nhiên hủy những phiên khác trên các thiết bị/nodes |
| `Local logout handler` | Dọn SecurityContext/session cục bộ của người dùng hiện hành | Không tự thông báo IdP hay toàn bộ SP khác |
| `SAML Single Logout` | Giao thức liên kết SP ↔ IdP, IdP có thể phối hợp các SP khác | Cần hỗ trợ metadata, signing, browser, và không đảm bảo mọi thiết bị/token |

Không dùng `SessionRegistry` như index phiên phân tán toàn cluster nếu thực tế chỉ là map in-memory một node. Nếu Spring Session/Redis quản lý nhiều replica, kiểm tra chính xác repository, event propagation và session expiration strategy. Đặc biệt, khi **SAML authentication** không đi qua cùng session-concurrency setup như username/password login trong project, cần xác minh registry có được populate đúng hay không.

## 12. Khóa ở IdP và khóa ở SP: nên làm gì khi trạng thái không đồng bộ?

Một sự kiện IAM có thể thay đổi:
- Account ở **IdP** (không cho xác thực mới);
- Record account ở **app** (chặn authorization);
- **Tập quyền** trong hệ HR/IAM và SP;
- Session IdP và SP;
- External API tokens hoặc long-lived connections.

Những thay đổi đó là **các hệ thống riêng**. Để bảo đảm không còn truy cập, chính sách tối thiểu là **SP có một nguồn kiểm soát hiện hành** và không cho phép account disabled, bất kể IdP có tạo SAMLResponse hợp lệ mới hay không.

### Nếu chỉ khóa IdP

- Với phiên SP active, có thể **chưa tác động** đến request tiếp theo.
- Khi session SP hết và browser đi IdP đăng nhập mới, IdP có thể từ chối nếu trạng thái khóa đã được áp dụng.
- Nếu IdP session còn và chính sách tài khoản khóa không được xét khi tái sử dụng SSO, cần kiểm tra IdP behavior; không suy “khóa tài khoản chắc chắn chặn mọi SSO có sẵn”.
- SP **không nên** phụ thuộc vào IdP tạo SAMLResponse lỗi để chặn **một phiên SP đã được xác thực**.

### Nếu chỉ khóa SP

- Session SP có thể bị xóa, request mới bị từ chối.
- IdP có thể vẫn có phiên, browser trở lại và nhận một SAMLResponse mới hợp lệ.
- SP phải **kiểm tra account disabled ngay khi cấp quyền/truy cập**; nếu không, user có thể tái tạo phiên.
- Không dùng SAML signature validity như bằng chứng account được phép sử dụng ứng dụng.

### Nếu cả hai cùng khóa

Tốt nhất là theo quy trình đáng tin:
1. IAM phát thay đổi được audit và version.
2. App áp dụng `disabled=true` vào nguồn kiểm soát.
3. Các cache/live authorizers nhận version mới hoặc không thể dùng snapshot cũ để allow.
4. App revoke các SP sessions và token thuộc phạm vi quản lý.
5. IdP khóa khả năng xác thực mới và thực hiện revocation/SLO nếu hỗ trợ.
6. Hệ thống kiểm tra end-to-end; báo phần nào chưa xác nhận.
7. Sự kiện lặp hoặc đảo thứ tự không được vô tình “mở khóa” account.

Đây là **thiết kế phối hợp**, không phải “Spring Security tự động gọi tất cả bước trên”.

## 13. SAML Single Logout có giải quyết mọi trường hợp không?

Spring Security hỗ trợ SAML 2.0 Single Logout (SLO) do SP hoặc IdP khởi tạo. Nó hữu ích để **phối hợp kết thúc những phiên SAML** giữa các bên tham gia, nhưng không thể thay cho live authorization:

- IdP phải công bố `SingleLogoutService` và các bên cấu hình SLO đúng.
- IdP-initiated SLO gửi một `LogoutRequest` đã được SP kiểm tra; SP có thể hủy local session phù hợp.
- Browser có thể đóng tab, không gửi cookie, hoặc ngắt redirect chain; SLO front-channel có thể không hoàn thành.
- Các ứng dụng không tham gia SLO và API tokens không được tự động revoke.
- SLO có thể gắn `NameID`/`SessionIndex`, phạm vi không nhất thiết mọi session của mọi thiết bị.
- Account lock/role change **không đồng nghĩa IdP chắc chắn phát SLO**. Hành vi này phụ thuộc chính sách/khả năng từng IdP.

**Kết luận:** với thu hồi quyền gấp, cần kiểm tra quyền hiện hành ở SP hoặc một revocation marker ngay trên request. SLO là biện pháp **bổ sung**, không phải điều kiện đủ duy nhất.

## 14. SAML assertion, AuthnInstant và “phiên có còn hợp lệ?”

Ba thời điểm khác nhau:

| Mốc | Nghĩa | Không nên suy |
| --- | --- | --- |
| `AuthnInstant` | IdP khẳng định thời điểm xác thực | Đó là thời điểm kiểm tra quyền hiện hành của app trên mọi request |
| `Conditions@NotOnOrAfter` | Thời hạn điều kiện assertion được SP đánh giá theo policy | HTTP session SP tự hết hạn đúng mốc ấy |
| `HttpSession lastAccessedTime/maxInactiveInterval` | Thời gian hoạt động/idle timeout của phiên SP | Account đã bị khóa thì request được chặn ngay |
| `IAM authorizationVersion` | Phiên bản quyền được phát hành theo nguồn authoritative | Tương đương SAML InResponseTo hoặc SAML SessionIndex |

Nếu requirement là “user không được phê duyệt sau khi quyền bị thu hồi ở 10:00”, kiểm tra quyền hiện hành vào **thời điểm phê duyệt** có giá trị hơn việc biết assertion phát lúc 09:00.

### ForceAuthn có giúp?

`ForceAuthn=true` trong `AuthnRequest` yêu cầu IdP xác thực lại trực tiếp theo SAML, **nhưng không tự refresh phiên đã tồn tại ở SP** khi không phát request mới. Nó cũng không đồng nghĩa MFA, không tự đồng bộ quyền ứng dụng và không thay đổi app-local account state. Nếu step-up là requirement riêng, cần xử lý thời gian/phương thức và ràng buộc giao dịch; còn revocation cần account/permission controls như ở trên.

## 15. Phiên active, yêu cầu đang chạy và khoảng trễ thu hồi

Một chính sách “thu hồi quyền có hiệu lực ngay” cần hiểu rõ ràng buộc thời gian.

Giả sử:
- 10:00:00 user bắt đầu yêu cầu POST phê duyệt.
- 10:00:01 AuthorizationFilter cho phép vì account còn quyền.
- 10:00:02 IAM phát event thu hồi.
- 10:00:03 service thực hiện commit phê duyệt.

Nếu chỉ kiểm tra quyền **một lần trước controller**, yêu cầu đang chạy có thể **vẫn commit sau khi quyền bị rút**. Tùy yêu cầu rủi ro, cần kiểm tra quyền tại thời điểm gần hành động quyết định, thậm chí cùng transaction với dữ liệu authorization.

Các lựa chọn:
1. **At-request check:** kiểm tra trên mỗi HTTP request; giới hạn window cho request mới.
2. **At-action check:** kiểm tra tại service method ngay trước thao tác nhạy cảm.
3. **At-commit/transactional check:** kết hợp version/lock/CAS trên account state trong transaction để tránh authorization race.
4. **Event revocation:** vô hiệu hóa sessions, nhưng không bảo đảm chặn request đã bắt đầu.
5. **Absolute TTL:** giới hạn thời gian stale tối đa, không thay revocation tức thì.

### Định nghĩa SLA rõ

Ví dụ:
- Quyền xem dữ liệu thường: độ trễ thu hồi ≤ 60 giây qua cache TTL.
- Quyền phê duyệt tài chính: request phải đọc current account state từ DB/PDP trước khi thực hiện, **fail closed** nếu không xác minh được.
- Khóa tài khoản vì bị xâm nhập: disable app account, invalidate sessions/tokens và theo dõi attempts/new logins.
- Các giá trị trên là **ví dụ chính sách**, không phải mặc định Spring Security hay yêu cầu tiêu chuẩn SAML.

Đừng hứa “tức thời trên mọi node” nếu thực tế hệ thống là eventual-consistent event bus và cache TTL 5 phút.

## 16. Cơ chế event-driven: SCIM/IAM push không phải SAML assertion mới

Một IdP có thể đồng thời cung cấp:
- SAML dùng cho **đăng nhập (authentication)**;
- SCIM dùng cho **provisioning/deprovisioning user/group**;
- Webhook/event stream, directory sync hoặc API quản trị;
- SLO dùng cho **federation logout**.

**Không đồng nhất SCIM với SAML SLO.** Một event khóa account qua SCIM hoặc HR update không tự là một LogoutRequest đã ký. Tương tự, một Login Assertion mới không phải bản cập nhật quyền cho toàn bộ phiên đã tạo.

Thiết kế event:

~~~mermaid
flowchart TD
    A[IAM/HR change: lock account or revoke permission] --> B[Publish authenticated versioned event]
    B --> C[Consumer verifies origin and account identity]
    C --> D[Persist disabled/permissions/version into authoritative app store]
    D --> E[Invalidate authz caches and sessions]
    E --> F[Revoke app tokens and long lived connections as required]
    F --> G[Audit and monitor all replicas]
    G --> H[Next request checks current state and denies if revoked]
~~~

### Dạng sự kiện tham khảo

~~~json
{
  "eventId": "revocation-example-001",
  "tenantId": "finance",
  "idpEntityId": "https://idp.example.org/issuer",
  "subjectId": "immutable-external-123",
  "version": 108,
  "state": "DISABLED",
  "permissions": [],
  "effectiveAt": "2026-11-07T10:00:00Z"
}
~~~

Đây là **JSON minh họa hợp đồng nội bộ**, không phải SAML protocol message hoặc SCIM chuẩn được áp dụng nguyên bản. Những yêu cầu thực tế:
- Producer và consumer được xác thực/ủy quyền (mTLS/signature, IAM roles, broker ACL).
- `eventId` chống xử lý lặp; `version` tạo ordering theo account.
- Account key phải gắn issuer/tenant và immutable subject; không dựa riêng vào email.
- Nếu event đến sai thứ tự, consumer không ghi đè trạng thái mới bằng version cũ.
- Nếu event bị mất, chạy **reconciliation job** đối chiếu nguồn quyền authoritative.
- Nếu event tạm lỗi, retry có backoff, dead-letter queue, cảnh báo và trạng thái fail-closed cho quyền nhạy cảm.
- Nếu quyền thay đổi nhiều lần nhanh, logic không được vô tình **mở lại account** vì một event stale.
- Trường dữ liệu cá nhân trong audit cần retention/permission, không ghi raw SAMLResponse.
- Khi thay role, không coi session cũ có những quyền trong `Authentication.getAuthorities()` là nguồn sự thật mới.

## 17. Kỹ thuật versioning quyền: tránh replay và stale cache

Gắn một `authorizationVersion` cho account theo nguồn authoritative:

~~~text
Version 21: enabled=true,  permissions=[READ, APPROVE]
Version 22: enabled=true,  permissions=[READ]
Version 23: enabled=false, permissions=[]
~~~

Một SP session được tạo lúc version 21 có thể lưu `authzVersionAtLogin=21`. Khi request đến:
1. Tìm account theo issuer/tenant/subject.
2. Nếu disabled, **deny** ngay.
3. Nếu version hiện hành lớn hơn version trong session, **không dùng authorities snapshot cũ để allow**. Có thể kiểm tra quyền live, yêu cầu refresh server-side, hoặc invalidate session.
4. Nếu store unavailable, áp dụng fail-closed cho những hành động rủi ro cao.
5. Ghi audit quyết định kèm version, không in raw username/permissions nếu nhạy cảm.

**Cảnh báo:** account-version không phải protocol token. Nếu dùng trong SecurityContext/session, đó chỉ là trạng thái cục bộ để so với nguồn thật; không tin `version` do browser cung cấp. Nếu một user được phép cấp lại quyền, version phải tăng chứ không reset làm event cũ trông mới.

### So sánh cache TTL và event

| Cơ chế | Thuận lợi | Giới hạn |
| --- | --- | --- |
| Cache TTL 30 giây | Đơn giản, giới hạn staleness khi nguồn luôn reachable | Có thể allow trong cửa sổ TTL; không phù hợp revocation tức thời |
| Push event + invalidate cache | Thường cập nhật nhanh, ít truy vấn | Có thể mất/chậm event, cần ack/retry/reconcile |
| Check DB/PDP mỗi hành động | Quyền gần thời điểm xử lý hơn | Độ trễ/availability, cần fail-closed và tối ưu |
| Version check ở cache phân tán | Giá rẻ, phát hiện session cũ | Version phải đến từ nguồn authoritative và đồng bộ |
| Session deletion | Ngăn tiếp tục phiên đã thu hồi | Không ngăn IdP SSO lại nếu thiếu account gate |

Một lựa chọn tốt thường kết hợp **event invalidate** với **read-through TTL/reconcile**, và kiểm tra trực tiếp DB ở giao dịch đặc biệt nguy hiểm.

## 18. Java 17 chạy độc lập: mô phỏng thu hồi quyền và khóa account

Chương trình sau chỉ dùng **Java 17 Standard Library**. Nó mô hình hóa session giữ **version quyền cũ** trong khi account store đã đổi. Kết quả minh họa vì sao **session còn tồn tại không có nghĩa còn quyền**. Nó không tự triển khai SAML, không tạo cookie/session HTTP, không xác minh XML Signature hay revoke Redis sessions.

Tệp `SessionRevocationDemo.java`:

~~~java
import java.util.Set;

public final class SessionRevocationDemo {

    record Session(String subject, long authorizationVersion,
                   boolean active) {
    }

    record Account(boolean enabled, long authorizationVersion,
                   Set<String> permissions) {
    }

    static String decide(Session session, Account current,
                         String requiredPermission) {
        if (!session.active()) {
            return "DENY_NO_SESSION";
        }
        if (current == null || !current.enabled()) {
            return "DENY_ACCOUNT_DISABLED";
        }
        if (session.authorizationVersion()
                != current.authorizationVersion()) {
            return "DENY_STALE_AUTHORIZATION";
        }
        if (!current.permissions().contains(requiredPermission)) {
            return "DENY_PERMISSION";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Session oldSession = new Session("subject-123", 7L, true);
        Account before = new Account(true, 7L,
                Set.of("READ", "APPROVE"));
        Account roleRemoved = new Account(true, 8L,
                Set.of("READ"));
        Account disabled = new Account(false, 9L,
                Set.of());

        System.out.println("Before: "
                + decide(oldSession, before, "APPROVE"));
        System.out.println("After role change: "
                + decide(oldSession, roleRemoved, "APPROVE"));
        System.out.println("After lock: "
                + decide(oldSession, disabled, "READ"));

        Session refreshed = new Session("subject-123", 8L, true);
        System.out.println("Refreshed without approve: "
                + decide(refreshed, roleRemoved, "APPROVE"));

        Session revoked = new Session("subject-123", 9L, false);
        System.out.println("Revoked: "
                + decide(revoked, disabled, "READ"));
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac SessionRevocationDemo.java
java SessionRevocationDemo
~~~

Stdout **chính xác**:

~~~text
Before: ALLOW
After role change: DENY_STALE_AUTHORIZATION
After lock: DENY_ACCOUNT_DISABLED
Refreshed without approve: DENY_PERMISSION
Revoked: DENY_NO_SESSION
~~~

**Giải thích kết quả:**
- Phiên version 7 ban đầu có quyền `APPROVE` và được allow.
- Khi quyền bị gỡ, version account tăng thành 8. Dù session cũ vẫn active, hệ thống **không dùng version 7 để phê duyệt**.
- Khi khóa account version 9, mọi permission bị từ chối theo trạng thái disabled.
- Sau khi làm mới phiên thành version 8 nhưng không có APPROVE, vẫn bị deny.
- Khi session bị revoke, bị từ chối trước khi xét account.
- Program chỉ mô phỏng policy. Production cần nguồn authoritative, chống race, multi-node consistency và kiểm tra permission từng resource.

**Lựa chọn chính sách khác:** thay vì `DENY_STALE_AUTHORIZATION` khi version không khớp, một ứng dụng có thể tự tra permission live và quyết định ngay trong cùng request, hoặc vô hiệu hóa session. Dù chọn gì, không dùng authorities cũ để tự động allow.

## 19. Quy trình khóa account an toàn trong production

Khi đội hỗ trợ xác định một user phải bị vô hiệu hóa khẩn cấp:

1. **Xác minh đối tượng:** xác định account nội bộ qua `(issuer/tenant, immutable subject)`, không nhầm người có email giống nhau.
2. **Ủy quyền:** chỉ role/admin/process được phép mới có quyền khóa; mọi yêu cầu khóa có audit.
3. **Ghi authoritative state trước:** đặt `enabled=false`, tăng `authorizationVersion` và commit.
4. **Đẩy cập nhật:** phát event đáng tin để các authorization caches và replicas invalidate.
5. **Revoke SP sessions:** tra indexed sessions đúng account, xóa/invalidate và xử lý token app nếu cần.
6. **Chặn re-login:** SAMLResponse mới từ IdP có chữ ký hợp lệ vẫn phải qua account gate; account locked sẽ không được sử dụng tài nguyên.
7. **Đồng bộ IdP:** nếu chính sách yêu cầu, khóa khả năng SSO mới và thu hồi IdP session theo cơ chế IdP hỗ trợ; không coi SLO luôn được phát.
8. **Kiểm thử sau sự kiện:** dùng một phiên SP cũ, thử request xem dữ liệu/POST nhạy cảm và đăng nhập lại để chắc đều bị chặn.
9. **Theo dõi propagation:** xem pod/cache/token nào chưa xác nhận, có retry/reconciliation và cảnh báo.
10. **Gỡ khóa có kiểm soát:** khi được cho phép, tăng version tiếp, khôi phục permission tối thiểu; không tự phục hồi quyền quản trị cũ chỉ vì user enabled lại.

Nếu event revoke đến muộn, lớp check authoritative state ở request vẫn phải đủ để chặn khi thực sự có hiệu lực. Nếu nguồn offline và nghiệp vụ nhạy cảm, fail closed; đừng tự mở truy cập do “directory timeout”.

## 20. Phân biệt 401, 403, redirect login và “chưa cập nhật giao diện”

Sau khóa account, user có thể gặp nhiều kết quả:

- **403 Forbidden:** request có authenticated principal nhưng không đủ quyền theo `AuthorizationManager` hoặc method security.
- **Redirect đến SAML login:** SP không còn session/Authentication sau revocation; entry point dẫn browser sang IdP.
- **SAML login quay về rồi 403:** IdP session còn và cấp response hợp lệ, nhưng app account gate vẫn chặn. Đây là dấu hiệu **SP chặn đúng**, không phải chứng minh khóa thất bại.
- **401 Unauthorized:** phổ biến ở API authentication entrypoint tùy cấu hình; không cố định cho mọi Spring MVC/SAML browser flow.
- **200 ở trang SPA đã cache:** UI vẫn hiển thị nút/record cũ trong browser, nhưng backend phải thực thi deny khi user hành động hoặc tải lại dữ liệu.

Không đồng nhất “ẩn nút” với “thu hồi quyền”. Frontend feature flag/menu là UX, **không phải authorization enforcement**. Người dùng có thể gọi API trực tiếp qua công cụ HTTP ngay cả khi nút không hiện.

### WebSocket và long-lived connections

Một WebSocket/STOMP session có thể được thiết lập khi account còn quyền. Nếu authorization chỉ kiểm tra lúc handshake, các message về sau có thể tiếp tục chảy qua kết nối dù account đã bị khóa. Cần:
- Authorization cho message/broker destination nếu app dùng Spring Security messaging;
- Cơ chế đóng kết nối khi revoke;
- Lựa chọn kiểm tra permission hiện hành cho thao tác nhạy cảm;
- Đánh giá queue consumer, job đã xếp hàng và task đang chạy.

Tương tự, nếu SAML login tại SP sau đó cấp một JWT cho API khác, **xóa HttpSession không tự revoke JWT đang còn hiệu lực**. Cần token lifetime, revocation list/introspection hoặc thiết kế khác tùy môi trường.

## 21. Kiểm thử end-to-end: role change khi session còn sống

**Chuẩn bị:** IdP test, SP test, tài khoản test có quyền duyệt giao dịch, account store có version, Redis/session index nếu muốn test revoke và browser DevTools. Không dùng tài khoản thật hoặc đụng hệ thống sản xuất cho negative tests.

### Test A — quyền bị gỡ, phiên chưa hết

1. Đăng nhập lúc quyền `PAYMENT_APPROVE` còn được cấp.
2. Xác nhận `POST /payments/approve` hoạt động khi dữ liệu hợp lệ.
3. Giữ nguyên cookie/browser, không logout.
4. Qua kênh IAM/admin test được ủy quyền, gỡ permission trong authoritative store và tăng version.
5. Gửi một POST mới đến cùng API với cookie cũ.
6. Kỳ vọng SP **không thực hiện hành động**; status cụ thể tùy policy (thường 403).
7. Kiểm tra DB không có tác dụng phụ, audit ghi deny và không dựa trên authorities snapshot cũ.
8. Nếu UI vẫn hiện nút, sửa UX riêng; backend vẫn phải enforce.

**Pass:** permission removal làm request nhạy cảm mới bị chặn mà không cần user chủ động logout.

### Test B — khóa tài khoản, vẫn giữ cookie

1. Login vào SP như user test.
2. Tại IAM/app store, đánh dấu account disabled, phát event và revoke sessions theo thiết kế.
3. Request bảo vệ dùng cookie SP cũ phải bị từ chối hoặc challenge.
4. Kiểm tra request đang chạy tại thời điểm khóa theo policy đã định.
5. Thử login lại: ngay cả khi IdP có thể SSO nhanh, app vẫn deny account disabled.
6. Xác minh cookie/session cũ không cấp quyền sau khi revive browser/restart app.

**Pass:** account disabled không thể dùng ứng dụng chỉ nhờ cookie/SP session cũ.

### Test C — nhiều thiết bị, nhiều node

1. Login account test từ Browser A, Browser B và Browser C, phân phối qua nhiều pod nếu có.
2. Revoke account, kiểm tra index tìm đúng các session thuộc account.
3. Gửi request đồng thời từ A/B/C sau thời điểm xác nhận revoke.
4. Tất cả phải chịu cùng policy deny, không có pod còn snapshot quyền cũ vô thời hạn.
5. Kiểm tra không xóa nhầm session của tenant/IdP khác có cùng username.
6. Audit thấy các session IDs đã được xử lý nhưng không hiển thị cookie/session ID cho user.

### Test D — sự kiện cũ đến sau sự kiện mới

1. Phát `version=10, enabled=false`.
2. Sau đó gửi lại event trùng lặp version 10 hoặc bản cũ version 9 enabled=true.
3. Store phải giữ disabled, không đảo chiều trạng thái.
4. Sau khi có event version 11 do admin được phép mở lại, chỉ những permission được cấp ở version 11 mới có hiệu lực.
5. Ghi audit source/version xử lý.

### Test E — IAM unavailable

1. Mô phỏng directory/authorization DB tạm không sẵn có.
2. Kiểm tra route cần quyền tài chính fail closed, không tự dùng role trong Authentication cũ.
3. Route public vẫn hoạt động theo policy, có thông báo lỗi/circuit breaker phù hợp.
4. Thử recovery; cache không được đọc state cũ quá mức policy cho phép.

### Test F — logout và SSO lại

1. Logout local SP, giữ IdP session.
2. Mở lại route: IdP có thể cấp SAMLResponse mới nếu IdP session còn.
3. Account disabled tại app phải tiếp tục bị deny.
4. Nếu business cần chặn IdP session, phối hợp IdP revocation/SLO riêng.
5. Không kết luận “logout thất bại” chỉ từ việc SSO lại nhanh; xem app authorization.

### Test G — request đang xử lý

1. Bắt đầu một thao tác xử lý lâu.
2. Gỡ quyền khi request đang ở giữa business logic.
3. Xác nhận policy quy định quyền còn được chấp nhận đến đâu.
4. Với thao tác rủi ro cao, kiểm tra at-commit hoặc transactional authorization tránh side effect sau revocation.
5. Không chỉ kiểm thử “request mới” rồi hứa mọi in-flight request cũng dừng.

## 22. Kiểm thử tự động bằng Spring Security Test

Khi dùng `@WebMvcTest` hoặc MockMvc trong project, cần phân biệt **mock Authentication** với **SAML login thật**:
- Unit test policy có thể dùng mock `Authentication` / `Saml2AuthenticatedPrincipal` với registrationId và stable subject test.
- Test MVC có thể dùng `SecurityMockMvcRequestPostProcessors.authentication(... )` hoặc security test framework theo version.
- Một mock user có authority `ROLE_ADMIN` **chưa chứng minh** Spring đã xử lý SAML Assertion đúng; nó chỉ test authorization.
- End-to-end test SAML còn cần IdP test, signed assertion/Response và trust.
- Test cần kiểm tra **side effects** không xảy ra sau khi quyền bị rút, không chỉ HTTP status.

Ví dụ một đoạn test định hướng (không phải test class độc lập):

~~~java
// Test setup creates an Authentication representing the test SAML user.
// The policy store initially has permission PAYMENT_APPROVE.
mockMvc.perform(post("/payments/approve").with(authentication(samlAuth))
        .with(csrf()))
       .andExpect(status().isOk());

// A trusted admin/provisioning update removes the permission.
accountPolicy.applyTrustedChange("corp", subject, true,
        Set.of("APP_ACCESS"), 2L);

mockMvc.perform(post("/payments/approve").with(authentication(samlAuth))
        .with(csrf()))
       .andExpect(status().isForbidden());
~~~

Điều kiện để mảnh test này chạy: có `MockMvc`, static imports `post`, `authentication`, `csrf`, `status`, một mock `samlAuth` hợp lệ và một controller/service test trả `200` khi được cho phép. Đây chỉ là **mảnh cấu trúc test**, không có các khai báo nên không thể copy chạy trực tiếp. Không cần tạo signed SAML assertion để test riêng `AccountPolicy`, nhưng phải có **integration test SAML** cho đường xác thực thật.

## 23. Những lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân thường thấy | Cách xử lý |
| --- | --- | --- |
| User bị gỡ quyền nhưng vẫn thấy admin API hoạt động | Chỉ dùng `hasRole` trên authorities snapshot | Check permission live hoặc version; thêm test quyền bị thu hồi |
| Account bị khóa ở IdP nhưng SP session còn hoạt động | IdP không thông báo/revoke SP session | Local disabled marker + revoke sessions + request gate |
| Sau revoke user SSO lại được ngay | Chỉ xóa SP session, IdP session còn | SP kiểm tra disabled, phối hợp IdP nếu cần logout tập trung |
| Role mới không xuất hiện tới lần login sau | Role mapper chỉ chạy khi nhận SAMLResponse | Chọn live permissions hoặc refresh/session invalidation có kiểm soát |
| Xóa session ở pod A nhưng pod B vẫn active | In-memory sessions/SessionRegistry không chung | Dùng distributed session store, index và chính sách nhất quán |
| Revoke nhầm người có cùng email | Identity key không có issuer/tenant | Dùng stable external subject + issuer/tenant và verify mapping |
| Event khóa bị event cũ mở lại | Consumer không so version | Monotonic version, idempotency, reject stale update |
| Authorization API down nhưng app vẫn allow quyền cũ | Fail-open hoặc cache không hạn chế | Fail-closed theo risk, retry/circuit breaker, stale policy |
| UI ẩn nút nhưng API vẫn được gọi | Frontend-only enforcement | Bắt buộc backend authorization |
| 403 sau SSO mới của user bị khóa | App disabled gate từ chối | Đây có thể là behavior đúng; phân biệt login và authorization |
| Account deletion nhưng job nền vẫn thực hiện | Job không dùng HttpSession/AuthorizationFilter | Kiểm tra quyền/identity tại execution boundary |
| Session hết hạn nhưng JWT vẫn valid | Token và HttpSession lifecycle riêng | Token revocation/short TTL/introspection |
| Socket vẫn nhận thông báo | WebSocket được auth lúc connect, không revoke | Đóng session/messaging authorization |
| SAML assertion còn hạn nhưng SP deny | Chính sách account app hiện tại chặn | Không nhầm deny với signature/issuer validation |
| POST bị 403 không phải do account lock | Thiếu CSRF token hoặc method security | Xem security logs/matcher/CSRF trước khi chẩn đoán |
| Restart app làm account state “mất” | Dùng in-memory ConcurrentMap như production | Chuyển authoritative data sang persistent store |
| Logout IdP không làm app bị khóa | SLO không cấu hình hoặc thiếu callback | SLO có giới hạn; cần kiểm soát access live |

## 24. Phân tích trước–sau: nhân viên chuyển bộ phận

### Trước

Một nhân viên thuộc nhóm `FINANCE_APPROVER` và đăng nhập portal SAML ngày thứ Hai. Quản trị viên chuyển họ sang bộ phận kiểm toán ngày thứ Ba; IdP gỡ group FINANCE_APPROVER, nhưng HTTP session ở portal vẫn được giữ. Ở portal, `SecurityContext` vẫn chứa authority cũ. Nếu service chỉ kiểm tra `hasAuthority("FINANCE_APPROVER")`, nhân viên có thể phê duyệt dù không còn quyền.

### Sau

1. Hệ thống IAM cập nhật quyền trong app authorization store theo immutable subject/tenant.
2. App phân biệt `Authentication` để xác định principal, sau đó check **current** `PAYMENT_APPROVE` trong service/policy.
3. IAM event invalidate cache hoặc session liên quan.
4. Request cũ không còn được phê duyệt; action đã bắt đầu được xử lý theo at-commit policy.
5. Người dùng vẫn có thể xem những tài nguyên được cấp theo quyền mới nếu account enabled; **không nhất thiết phải khóa toàn bộ tài khoản** chỉ vì gỡ một permission.

**Bài học:** “thu hồi một quyền” và “hủy mọi session” là hai hành vi khác nhau. Có thể giữ session và cập nhật authorization live, hoặc buộc login lại tùy chính sách; nhưng không để những thao tác nhạy cảm dùng snapshot cũ.

## 25. Phân tích trước–sau: tài khoản bị khóa vì rủi ro

### Trước

Security team khóa account tại IdP sau khi nghi ngờ lộ thông tin. Ứng dụng SP vẫn giữ session 8 giờ và không nhận trạng thái khóa. User/attacker đang có cookie SP vẫn gọi API được. Việc người đó không thể đăng nhập mới **không đủ** để bảo vệ phiên SP active.

### Sau

1. Sự kiện IAM/incident response tạo `disabled=true` trên app authoritative store trước khi phát action revoke.
2. SP check current disabled marker ở mọi route bảo vệ có yêu cầu account active.
3. App xóa/revoke các session SP (và token/connection phù hợp) qua identity key được xác minh.
4. IdP đồng thời khóa account và hủy session IdP theo khả năng sản phẩm; SLO chỉ là biện pháp cộng thêm.
5. Các request mới bị deny kể cả cookie còn hoặc IdP phát SAMLResponse mới.
6. Incident team xác minh trên nhiều node/devices, xử lý in-flight transaction theo rủi ro và không log dữ liệu định danh nhạy cảm.

**Bài học:** với khóa khẩn cấp, **deny at request/action** mới là rào chắn cuối quan trọng. Session invalidation giảm thời gian/cơ hội tái sử dụng, nhưng không tự cập nhật mọi hệ thống khác.

## 26. Một policy mẫu để chọn chiến lược

| Yêu cầu | Chiến lược ưu tiên | Tránh |
| --- | --- | --- |
| Portal công khai/nội dung không nhạy cảm | Session timeout hợp lý, basic current account gate | Coi timeout là account revocation tức thì |
| Hệ nội bộ HR/Finance | Live permission check ở HTTP/service + event invalidation | Chỉ dùng role trong SAML assertion cũ |
| Tài chính có lệnh không đảo ngược | Check quyền hiện hành gần commit + transaction guard | Chỉ kiểm tra khi browser mở trang |
| Khóa khẩn cấp khi bị tấn công | Disable authoritative account + revoke sessions/tokens + deny new SSO | Chỉ gọi IdP logout và tin mọi ứng dụng sẽ dừng |
| Multi-tenant/multi-IdP | Scoped identity key, issuer/tenant + immutable external ID | Email/NameID transient làm global key |
| Nhiều pod và thiết bị | Distributed indexed session store, consistent authz, reconciliation | In-memory registry trên một node như nguồn toàn cluster |
| Quyền thay đổi thường xuyên | Authz DB/PDP/cache có TTL/version/event | Re-login SAML ở mọi request |
| UX cần cập nhật ngay sau khi bị revoke | Server-side deny + event/UI update | Ẩn nút mà không kiểm tra backend |
| SSO từ IdP chưa có SLO | App-local state gate + revocation | Tự phát LogoutRequest tới URL IdP đoán mò |
| IdP chỉ xử lý disable khi login mới | App nhận IAM event/poll authoritative state | Cho session SP cũ hoạt động đến idle timeout |

## 27. Checklist triển khai

- [ ] Đã tách rõ SAML **authentication** với app **authorization** và thời điểm quyền có hiệu lực.
- [ ] Mọi route nhạy cảm kiểm tra enabled/locked và permission **hiện hành**, không chỉ `GrantedAuthority` từ lúc login.
- [ ] Danh tính định vị account dựa trên **IdP/issuer + tenant + immutable subject** đã được xác minh.
- [ ] Không suy username/email/NameID transient mặc định là globally unique.
- [ ] Có cơ chế provisioning/deprovisioning hoặc API/DB kiểm tra current state, không mong SAML tự push.
- [ ] Sự kiện IAM được xác thực, idempotent, version monotonic, có retry/reconcile/audit.
- [ ] Quyết định có SLA revocation và fail-closed khi quyền rủi ro cao không thể kiểm tra.
- [ ] Trong multi-node, cache trạng thái và session store có consistency phù hợp.
- [ ] Session lookup/revoke chỉ do admin/process có quyền; không xóa nhầm session người khác.
- [ ] Có bảo vệ chống event replay/out-of-order và không dùng timestamp client làm quyền phát hành.
- [ ] Sau account lock, SSO mới vẫn phải chịu app disabled policy kể cả IdP cookie còn.
- [ ] Không coi SAML SLO là bảo đảm logout mọi phiên/thiết bị/token.
- [ ] Method-level và object-level authorization che chắn business logic, kể cả nguồn gọi ngoài MVC.
- [ ] Nếu cần tức thời, có xử lý in-flight action và check gần commit.
- [ ] WebSocket, queue consumer, API tokens/refresh tokens có cơ chế revoke/authorization riêng.
- [ ] Test thay quyền khi session đang active, khóa account, nhiều browser/node, IdP session còn, store down, event stale.
- [ ] Không log raw SAMLResponse, session cookie, JWT, NameID/subject thật hoặc account permissions nhạy cảm ra nơi công khai.
- [ ] Giữ signature, issuer, audience, destination, subject/time và `InResponseTo` validation của SAML login; không làm yếu đi vì cần dynamic authorization.

## 28. Câu hỏi ôn tập kèm đáp án

**Bài 1.** IdP bỏ group ADMIN lúc 10:00 nhưng user login SP từ 09:00. Nếu SP chỉ dùng `hasAuthority("ADMIN")` trên Authentication đã lưu, quyền có chắc biến mất lúc 10:01 không?

**Đáp án:** không. Authorities có thể là snapshot. Phải có live authorization, refresh/revoke hoặc version check để chính sách mới có hiệu lực.

**Bài 2.** Khóa account tại IdP có tự xóa cookie `JSESSIONID` của mọi ứng dụng SP không?

**Đáp án:** không có bảo đảm mặc định. IdP và SP giữ phiên riêng. Có thể dùng SLO/phối hợp revocation, nhưng SP cần account gate để từ chối request hiện hành.

**Bài 3.** SP xóa tất cả HttpSessions đang index theo user, nhưng IdP SSO session còn. Người dùng quay về portal được login lại ngay. Giải pháp nào ngăn truy cập nếu account vẫn disabled?

**Đáp án:** kiểm tra account disabled/permissions **tại SP** trên login/use, không chỉ xóa session.

**Bài 4.** Tại sao tăng session idle timeout lên 8 giờ lại làm vấn đề stale role tồi tệ hơn?

**Đáp án:** phiên có thể sống lâu hơn sau thay quyền; nếu chỉ sử dụng authorities snapshot, cửa sổ quyền cũ có thể tăng. Cần live gate/revocation, không chỉ tùy chỉnh timeout.

**Bài 5.** Khi nào `SessionRegistry.expireNow()` chưa đủ?

**Đáp án:** nếu registry không nhìn thấy mọi session, thiếu `ConcurrentSessionFilter`, nhiều node không chia sẻ trạng thái hoặc request đã in-flight. Cần kiểm tra cấu hình và kết hợp live authorization.

**Bài 6.** Có thể xóa session theo email nếu hai IdP khác nhau cùng cấp một email giống nhau không?

**Đáp án:** nguy hiểm. Phải bảo đảm identity mapping scoped theo issuer/tenant và immutable subject hoặc principal key toàn cục không va chạm.

**Bài 7.** Người dùng đã authenticated nhưng bị HTTP 403 sau khi quyền bị thu hồi. Có phải IdP SAML Response đã hết hạn không?

**Đáp án:** không nhất thiết. Đây có thể là kết quả **authorization live** từ chối; phân biệt với SAML login validation.

**Bài 8.** Sự kiện IAM version 20 disabled đến trước, version 19 enabled đến sau. Consumer nên làm gì?

**Đáp án:** giữ version 20, bỏ sự kiện version thấp hơn. Nếu reset thành enabled, sẽ mở khóa trái ý định.

**Bài 9.** Nếu quyền phê duyệt bị thu hồi sau khi AuthorizationFilter đã cho phép nhưng trước khi transaction commit, có nên chỉ dựa vào kiểm tra ở filter?

**Đáp án:** không nếu nghiệp vụ yêu cầu revocation đến thời điểm commit. Cần at-action/transactional check, đồng bộ dữ liệu và chính sách xử lý in-flight.

**Bài 10.** Có cần bật `@EnableMethodSecurity` để `@PreAuthorize` chạy trong Spring Boot không?

**Đáp án:** có; Spring Boot Starter Security không tự bật method-level authorization ở mọi project.

**Bài 11.** SAML Single Logout có thu hồi mọi JWT được app khác phát không?

**Đáp án:** không tự động. JWT/API token cần cơ chế lifecycle, expiry và revocation riêng.

**Bài 12.** Cache authorization stale trong 5 phút, nhưng chính sách yêu cầu khóa khẩn cấp có hiệu lực trong 10 giây. Đã đáp ứng chưa?

**Đáp án:** chưa. Cần thiết kế độ trễ thấp với invalidation và/hoặc check authoritative state, fail-closed, giám sát theo SLA.

**Bài 13.** User bị gỡ quyền APPROVE nhưng vẫn được phép READ. Có nhất thiết logout toàn bộ user khỏi mọi ứng dụng không?

**Đáp án:** không. Có thể tiếp tục cho READ với quyền hiện hành; mục tiêu là chặn APPROVE. Hành vi revoke session phụ thuộc chính sách và UX.

**Bài 14.** User bị disable ở SP nhưng IdP vẫn ký SAMLResponse hợp lệ. Có được mở lại quyền truy cập vì chữ ký hợp lệ không?

**Đáp án:** không. Chữ ký chỉ giúp xác minh nguồn/thông điệp; SP vẫn phải áp dụng account disabled policy.

**Bài 15.** Một service job chạy với system account chứ không có session browser gọi phương thức approve. `AuthorizationFilter` có bảo vệ job không?

**Đáp án:** không mặc định. Phải dùng authorization ở service/business boundary, phân biệt quyền của system account và user thay mặt, audit và transaction policy.

## 29. Ghi nhớ

**SAML assertion xác minh một sự kiện đăng nhập; Spring Security session lưu Authentication; quyền và trạng thái tài khoản có thể thay đổi sau khi phiên đó được tạo.** Vì vậy, khóa account hoặc gỡ role ở IdP **không tự cập nhật mọi phiên SP đã tồn tại**. Muốn thay đổi có hiệu lực, SP phải áp dụng **trạng thái/quyền hiện hành trên request/action**, kết hợp **session/token revocation**, quản lý **độ trễ cập nhật** và chặn cả những lần SSO mới từ IdP nếu account local đã bị vô hiệu hóa.

Một sơ đồ ngắn:

~~~text
IAM thay đổi account/role
    -> app authoritative state + version được cập nhật
    -> cache/session/token được invalidate theo yêu cầu
    -> request/operation tiếp theo kiểm tra trạng thái hiện hành
    -> ALLOW nếu enabled và có quyền, DENY nếu revoked/disabled
~~~

Không lấy `Authentication.getAuthorities()` cũ hoặc một SAMLResponse đã ký làm nguồn quyết định quyền bất biến cho toàn bộ đời phiên.

### Tài liệu chính thức tham khảo

- Spring Security — SAML 2.0 Login Overview, cách tạo Saml2Authentication/SecurityContext: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authentication Persistence and Session Management, SecurityContextRepository và SessionRegistry: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authorize HttpServletRequests, AuthorizationFilter/AuthorizationManager: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security, EnableMethodSecurity/PreAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Performing SAML 2.0 Single Logout, RP/AP flows and limits: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Session — Redis Configurations, Finding All Sessions of a Specific User: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session — API Documentation, SessionRepository/FindByIndexNameSessionRepository: https://docs.spring.io/spring-session/reference/api.html
- Spring Security API — Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
