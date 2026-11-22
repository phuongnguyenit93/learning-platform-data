# Trách nhiệm của Spring Security, máy chủ danh tính và hệ thống nghiệp vụ trong Federation

## 1. Hiểu đúng bài toán

**Federation (liên kết danh tính)** cho phép một ứng dụng tin vào kết quả xác thực do một hệ thống danh tính khác cung cấp, theo một quan hệ tin cậy và giao thức được cấu hình trước. Ví dụ: nhân viên đăng nhập ở hệ thống danh tính của doanh nghiệp (Identity Provider, viết tắt **IdP**) rồi truy cập nhiều ứng dụng nội bộ mà không cần tạo mật khẩu riêng cho từng ứng dụng. Trải nghiệm này thường được gọi là **Single Sign-On (SSO)**.

Ba câu hỏi khác nhau phải được trả lời ở ba nơi thích hợp:

1. **Người đang đăng nhập là ai, được xác minh bằng cách nào?** Trọng tâm của IdP và quá trình xác thực.
2. **Ứng dụng có chấp nhận kết quả xác thực/token và cho phép đi đến chức năng nào?** Trọng tâm của Spring Security được cấu hình trong từng ứng dụng/API.
3. **Người đó có quyền xem hóa đơn A, sửa đơn hàng B, phê duyệt giao dịch C hay truy cập dữ liệu của tenant X không?** Trọng tâm của **hệ thống nghiệp vụ**, dựa trên dữ liệu và chính sách của nó.

Cần phân biệt hai thuật ngữ:

- **Authentication (xác thực, AuthN):** xác lập danh tính của người dùng hoặc ứng dụng gọi API.
- **Authorization (phân quyền, AuthZ):** quyết định danh tính đã xác thực được thực hiện hành động nào trên tài nguyên nào. Có đăng nhập thành công không đồng nghĩa có quyền với mọi dữ liệu.

Spring Security là **framework bảo mật chạy bên trong ứng dụng Spring**, không mặc nhiên là một IdP tập trung. IdP cũng không tự biết toàn bộ quy tắc nghiệp vụ của từng hệ thống.

## 2. Các thành phần trong kiến trúc liên kết

| Thành phần | Vai trò | Ví dụ trách nhiệm |
| --- | --- | --- |
| Người dùng / trình duyệt | Khởi tạo đăng nhập và sử dụng ứng dụng | Chuyển hướng đến IdP, gửi lại authorization code hoặc SAML response theo luồng |
| **Identity Provider (IdP)** | Xác minh danh tính, quản lý phiên đăng nhập tập trung | Mật khẩu, passkey, MFA, chính sách đăng nhập, thông tin danh tính, sự kiện đăng nhập |
| **Authorization Server** | Cấp và quản lý token OAuth 2.0 | Client registration, authorization code, access token, refresh token, scopes, khóa ký, endpoint metadata/introspection |
| **Spring Security trong ứng dụng web** | Làm OAuth 2.0/OIDC client hoặc SAML relying party | Khởi động luồng đăng nhập, kiểm tra phản hồi, xây dựng Authentication, bảo vệ phiên và route |
| **Spring Security trong API** | Làm OAuth 2.0 Resource Server | Xác minh access token JWT hoặc introspection token, tạo principal/authorities, bảo vệ endpoint |
| **Ứng dụng và dịch vụ nghiệp vụ** | Sở hữu quyền nghiệp vụ và dữ liệu | Liên kết danh tính với tài khoản nội bộ, tenant, role nghiệp vụ, quyền trên từng bản ghi, audit nghiệp vụ |
| API Gateway (nếu có) | Lớp kiểm soát biên | TLS, rate limit, routing, có thể kiểm tra token ở biên; không thay thế kiểm tra tại API |

Trong sản phẩm thực tế, **IdP và Authorization Server có thể nằm chung một nền tảng** (chẳng hạn một hệ thống OIDC). Nhưng đây vẫn là hai *vai trò logic*: IdP xử lý việc chứng minh danh tính; Authorization Server cấp token để client truy cập tài nguyên. Một hệ thống có thể đồng thời đóng nhiều vai trò, song ranh giới trách nhiệm vẫn cần rõ.

**Relying Party (RP)** là ứng dụng tin vào kết quả xác thực OIDC; **Service Provider (SP)** là thuật ngữ thường gặp phía ứng dụng SAML. **Resource Server** là API nhận access token. Một ứng dụng Spring Boot có thể vừa phục vụ trang web vừa phục vụ API, nhưng hai loại request có nhu cầu bảo mật khác nhau.

## 3. Bảng phân công trách nhiệm cụ thể

| Công việc/câu hỏi | IdP / Authorization Server | Spring Security tại ứng dụng | Hệ thống nghiệp vụ |
| --- | --- | --- | --- |
| Lưu và xác minh mật khẩu, passkey | **Chủ trì** | Chuyển hướng/tiếp nhận kết quả; không cần lấy mật khẩu IdP | Không lưu mật khẩu IdP |
| MFA, khóa tài khoản danh tính, rủi ro đăng nhập | **Chủ trì**, theo chính sách trung tâm | Có thể yêu cầu/kiểm tra tín hiệu xác thực mạnh khi cần | Quy định hành động nào cần bước xác minh mạnh hơn |
| Cấp authorization code, ID/access/refresh token | **Chủ trì**, tùy giao thức | Nhận, trao đổi, xác minh và sử dụng theo vai trò client/API | Không tự ký token thay IdP nếu không được thiết kế làm AS |
| Kiểm tra chữ ký, issuer, thời hạn, audience | Cung cấp metadata, khóa và nội dung token | **Thực thi kiểm tra token/assertion nhận được**, theo cấu hình | Chỉ xử lý danh tính/claims đã được tin cậy |
| Ánh xạ scope/group thành authority ứng dụng | Có thể phát hành scope/group/claim | Ánh xạ và áp dụng quy tắc endpoint/method | Định nghĩa ý nghĩa nghiệp vụ, giới hạn của quyền |
| Ai xem được hóa đơn số 123? | Thường không biết bản ghi đó | Có thể gọi điểm kiểm tra bảo mật | **Quyết định bằng dữ liệu sở hữu, tenant, quan hệ và chính sách** |
| Tài khoản nội bộ, trạng thái hội viên, phòng ban áp dụng trong app | Cung cấp thuộc tính danh tính nếu có | Truyền danh tính đã xác thực | **Ánh xạ, đồng bộ và quản lý vòng đời trong ứng dụng** |
| Session đăng nhập từng ứng dụng | Quản lý phiên SSO ở IdP | Quản lý/kiểm tra session tại ứng dụng web nếu dùng session | Quy định khi nào yêu cầu đăng nhập lại/thu hồi quyền |
| Nhật ký và điều tra | Nhật ký xác thực/phát token | Dấu vết xác thực và quyết định của lớp bảo vệ | Nhật ký truy cập dữ liệu và giao dịch nghiệp vụ |
| Từ chối một request | Có thể từ chối đăng nhập/cấp token | Trả 401/403 hoặc redirect theo cấu hình và ngữ cảnh | Từ chối khi không đủ điều kiện nghiệp vụ |

**Điểm mấu chốt:** IdP trả lời “đã xác minh ai và cho phép token mang những claim nào”; Spring Security trả lời “request này mang danh tính/tư cách bảo mật hợp lệ không, có vượt qua luật endpoint/method không”; nghiệp vụ trả lời “được thao tác trên đối tượng cụ thể này không”. Cùng một câu trả lời cuối cùng có thể cần **cả ba lớp**.

## 4. Trách nhiệm của máy chủ danh tính

Một IdP thường:

- Quản lý danh tính hoặc tích hợp với directory của tổ chức; xác minh tài khoản bằng mật khẩu, passkey, yếu tố thứ hai, điều kiện thiết bị hoặc đăng nhập từ IdP khác.
- Duy trì phiên SSO trung tâm và chính sách xác thực (MFA, giới hạn số lần thử, khôi phục tài khoản).
- Khi triển khai OIDC/OAuth 2.0, công bố **issuer**, discovery metadata, JWKS/public key; cấp token theo client, scope và chính sách; thực hiện xoay vòng khóa và có thể hỗ trợ revocation/introspection.
- Truyền claim được thỏa thuận, ví dụ subject ổn định, email, tên hiển thị, nhóm, tổ chức hoặc mức xác thực; chỉ truyền thuộc tính cần thiết và được phép.
- Quản trị vòng đời danh tính: tạo, khóa, xóa tài khoản hoặc đồng bộ với nguồn nhân sự. Tác dụng đối với phiên/token **đã cấp** còn tùy cơ chế thu hồi và thời hạn token.

Giới hạn của IdP: có thể biết người dùng thuộc nhóm `finance`, nhưng thường **không biết** hóa đơn nào thuộc chi nhánh nào, ai đang giữ quyền duyệt lô thanh toán nào hoặc một đơn hàng đang ở trạng thái khóa. Nếu tổ chức đưa chính sách nghiệp vụ vào hệ thống phân quyền tập trung, đó là tích hợp **được thiết kế rõ ràng**, không phải quyền mặc định của IdP.

## 5. Trách nhiệm của Spring Security trong từng ứng dụng

Spring Security cung cấp cơ chế để ứng dụng thực hiện và áp dụng bảo mật:

1. **Đón request:** `SecurityFilterChain` xử lý request trước controller; lựa chọn chuỗi filter theo URL và kiểu ứng dụng.
2. **Kết nối giao thức:** `oauth2Login()` cho đăng nhập OAuth 2.0/OIDC; `saml2Login()` cho SAML 2.0; `oauth2ResourceServer()` cho API nhận bearer access token; OAuth 2.0 Client cho việc ứng dụng lấy token gọi dịch vụ khác.
3. **Xác thực dữ liệu nhận được:** xử lý callback OIDC/SAML, kiểm tra token/assertion theo giao thức; API có thể xác minh JWT bằng khóa công khai hoặc gọi introspection endpoint với opaque token.
4. **Biểu diễn principal:** chuyển danh tính/claims hợp lệ thành `Authentication`, `GrantedAuthority` và ngữ cảnh bảo mật (`SecurityContext`).
5. **Áp dụng luật kỹ thuật:** ví dụ `authenticated()`, `hasAuthority("SCOPE_reports.read")`, `@PreAuthorize`, kiểm soát CSRF cho các luồng dùng cookie/session, quản lý session và cơ chế xử lý từ chối.
6. **Cho phép mở rộng:** mapping claims/groups thành authority nội bộ, validator bổ sung, trình xử lý thành công/thất bại đăng nhập, tích hợp với dịch vụ phân quyền.

Spring Security **không tự tạo tài khoản nghiệp vụ**, không thể suy đoán `tenantId` được quyền truy cập, không biến một scope thành quyền sở hữu mọi bản ghi và không tự cung cấp SSO đa ứng dụng khi chưa có IdP và cấu hình trust.

Nếu doanh nghiệp muốn **tự xây Authorization Server/IdP**, có thể sử dụng **Spring Authorization Server** làm nền tảng chuyên biệt. Đây là lựa chọn kiến trúc riêng, không phải hiệu ứng tự động của việc thêm `spring-boot-starter-security` vào ứng dụng.

## 6. Trách nhiệm của hệ thống nghiệp vụ

Ngay sau khi Spring Security đã xác thực request, hệ thống nghiệp vụ vẫn phải:

- **Liên kết danh tính ngoài với người dùng nội bộ:** dùng cặp `(iss, sub)` của OIDC/JWT làm khóa danh tính tin cậy theo issuer; với SAML dùng định danh được thỏa thuận. Không mặc định dùng email làm khóa bất biến vì email có thể đổi hoặc tái cấp.
- **Xác định ngữ cảnh tenant/tổ chức:** người dùng thuộc tenant nào, membership nào còn hiệu lực, tổ chức nào đang được chọn và từng chức năng hỗ trợ cross-tenant hay không.
- **Quản lý role và permission thực tế:** `FINANCE_REVIEWER`, `INVOICE_APPROVE`, giới hạn tiền, vùng quản lý, người duyệt thay thế, quyền theo trạng thái giao dịch.
- **Kiểm tra tài nguyên cụ thể:** tránh lỗ hổng IDOR/BOLA. Phải kiểm tra đối tượng được tải từ cơ sở dữ liệu thuộc tenant và quan hệ được cấp phép; không chỉ kiểm tra rằng người dùng có token hợp lệ.
- **Xử lý vòng đời nội bộ:** tạo tài khoản khi đăng nhập lần đầu nếu được phép (JIT provisioning), vô hiệu hóa quyền khi rời tổ chức, xử lý thay đổi membership và quyền thu hồi.
- **Định nghĩa nghiệp vụ và bằng chứng kiểm toán:** ai được phép làm gì, vì sao, trên bản ghi nào và khi nào. Không ghi lại access token/refresh token đầy đủ trong log.

**Ví dụ:** IdP xác nhận Alice là nhân viên và có claim `groups=["finance"]`. Spring Security xác minh token rồi ánh xạ thành quyền truy cập `/api/invoices/**` phù hợp. Dịch vụ hóa đơn tiếp tục xác định Alice thuộc tenant A và chỉ được đọc hóa đơn A-001; khi cố truy cập hóa đơn B-002 thuộc tenant B, dịch vụ **phải từ chối**. Đăng nhập và scope hợp lệ vẫn không cấp quyền xuyên tenant.

## 7. Federation qua OIDC, OAuth 2.0 và SAML 2.0

| Cơ chế | Mục tiêu chính | Thông điệp chính | Vai trò Spring Security |
| --- | --- | --- | --- |
| **OpenID Connect (OIDC)** | Xác thực người dùng trên nền OAuth 2.0 | ID token, có thể có UserInfo và access token | Ứng dụng web làm OIDC Relying Party qua OAuth 2.0 Login |
| **OAuth 2.0** | Ủy quyền client truy cập protected resource | Access token với quyền/phạm vi được cấp | OAuth 2.0 Client hoặc Resource Server; OAuth 2.0 tự thân không phải đặc tả “đăng nhập người dùng” |
| **SAML 2.0 Web SSO** | Liên kết đăng nhập qua SAML assertion | AuthnRequest / SAMLResponse (thường qua trình duyệt) | Ứng dụng làm SAML Service Provider/Relying Party qua `saml2Login()` |

Dùng OIDC khi ứng dụng cần danh tính người dùng và đăng nhập hiện đại qua IdP hỗ trợ OIDC. Dùng OAuth 2.0 Resource Server khi API cần kiểm tra access token. Dùng SAML 2.0 khi tích hợp SSO với đối tác/hạ tầng yêu cầu SAML. Không gửi SAML assertion hoặc OIDC **ID token** làm access token tới API.

Federation nhiều tầng có thể xuất hiện: ứng dụng tin IdP A, IdP A liên kết với IdP B của đối tác. Ứng dụng phải dựa trên **issuer/claim và chính sách trust đã thỏa thuận** với A; không tự tin một token bất kỳ do B phát hành khi chưa cấu hình nhà phát hành hợp lệ.

## 8. Luồng đăng nhập OIDC giữa ba bên

Giả sử ứng dụng web `portal.example.test` sử dụng IdP `login.example.test` và API nghiệp vụ.

1. Người dùng mở trang cần đăng nhập. Spring Security nhận thấy ứng dụng chưa có phiên xác thực, nên bắt đầu luồng đăng nhập tới IdP.
2. Trình duyệt được chuyển đến authorization endpoint với thông tin client, redirect URI, scope có `openid`, `state` và các tham số phòng chống tấn công theo luồng. Với Authorization Code, **PKCE** được dùng theo cấu hình/khả năng của client; OIDC có cơ chế `nonce` để gắn kết ID token với yêu cầu.
3. **IdP** tự xác minh người dùng bằng phương thức phù hợp (có thể yêu cầu MFA) và xét chính sách client. Ứng dụng không nhận mật khẩu IdP.
4. IdP chuyển trình duyệt về redirect URI đã đăng ký với **authorization code**. Phần OAuth 2.0/OIDC client của Spring Security xử lý callback, kiểm tra trạng thái giao dịch và đổi code lấy token qua token endpoint.
5. Spring Security và các thành phần OIDC liên quan xác minh ID token theo giao thức (issuer, audience/client, thời hạn, nonce khi áp dụng, chữ ký...) rồi tạo principal/Authentication. Ứng dụng web thường tạo **session riêng** cho lần đăng nhập này.
6. **Hệ thống nghiệp vụ** ánh xạ `iss + sub` với tài khoản nội bộ, kiểm tra active membership và chỉ cấp các tính năng phù hợp. Nếu mapping hoặc điều kiện nghiệp vụ không đạt, ứng dụng có thể từ chối dù IdP vừa đăng nhập thành công.
7. Khi trang gọi một **API** bằng bearer access token, API đóng vai Resource Server: xác thực token hợp lệ cho chính API, kiểm tra scope/authority, sau đó dịch vụ nghiệp vụ kiểm tra tenant và quyền trên bản ghi.

Một phiên SSO tại IdP, một session ứng dụng web và một access token API là **ba trạng thái khác nhau**. Logout ở một nơi không tự bảo đảm đã chấm dứt mọi nơi; cần thiết kế local logout, OIDC/SAML logout, hạn token và thu hồi quyền phù hợp.

## 9. Access token, ID token, refresh token và claim

| Loại | Dùng để làm gì | Nơi nhận đúng |
| --- | --- | --- |
| **ID token (OIDC)** | Chứng minh sự kiện xác thực và thông tin danh tính cho OIDC client | OIDC Relying Party có `client_id` khớp |
| **Access token** | Ủy quyền gọi resource/API trong phạm vi đã cấp | Resource Server có audience/contract phù hợp |
| **Refresh token** | Yêu cầu Authorization Server phát access token mới theo chính sách | OAuth client được phép; lưu giữ và bảo vệ chặt, không gửi vào API nghiệp vụ |

Các claim thường gặp:

- `iss`: nhà phát hành; phải nằm trong danh sách tin cậy, khớp cấu hình.
- `sub`: định danh subject do issuer cung cấp; thường dùng cùng `iss`.
- `aud`: đối tượng nhận token. **Access token cấp cho API A không được tự động chấp nhận tại API B.**
- `exp`, `nbf`, `iat`: mốc thời gian; cần kiểm soát hết hạn, chưa hợp lệ và clock skew phù hợp.
- `scope` hoặc `scp`: phạm vi quyền được cấp cho client/token, không thay thế quyền trên từng đối tượng dữ liệu.
- `groups`, `roles`, `tenant`: claim mở rộng theo nhà cung cấp; **ý nghĩa, nguồn tin cậy và cách ánh xạ phải được quy định rõ**.

JWT có thể **giải mã phần payload** mà không có khóa; giải mã **không phải xác minh chữ ký**. Một API cấu hình JWT Resource Server cần kiểm tra chữ ký, thời gian, issuer và **audience của chính API** theo cấu hình. Với `issuer-uri`, Spring Security hỗ trợ xác minh issuer và thời gian; trong ứng dụng cần cấu hình audience/validator phù hợp chứ không mặc định cho rằng audience luôn được bảo vệ.

Với opaque token (hoặc token muốn kiểm tra trạng thái trực tuyến), Resource Server có thể gọi **introspection endpoint**. JWT xác minh cục bộ thường giảm phụ thuộc trực tuyến, nhưng token đang còn hạn không mặc nhiên bị từ chối ngay khi tài khoản ở IdP bị khóa; cần chiến lược TTL, thu hồi, introspection và cập nhật quyền nghiệp vụ.

## 10. Ví dụ cấu hình Spring Boot: web đăng nhập OIDC, API nhận JWT

Ví dụ dưới đây minh họa **hai trách nhiệm trong cùng một ứng dụng Spring Boot dùng Spring Security Servlet**. Java 17+; cần các dependency tương ứng: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client` và `spring-boot-starter-oauth2-resource-server`. Dự án phải đăng ký client/redirect URI với IdP và thay mọi địa chỉ `example.test` bằng endpoint thực; đây là cấu hình tích hợp, không phải hệ thống có thể đăng nhập khi chưa kết nối IdP.

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
        provider:
          corp:
            issuer-uri: https://login.example.test/realms/work
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/work
          audiences: https://api.example.test
```

IdP phải có redirect URI đã đăng ký phù hợp, thông thường là `{baseUrl}/login/oauth2/code/corp`. Trong môi trường thật, dùng secret manager/biến môi trường cho client secret, HTTPS và URL issuer chính xác. `audiences` chỉ API được thiết kế nhận token; nếu phiên bản Boot không hỗ trợ property này, định nghĩa `OAuth2TokenValidator<Jwt>` kiểm tra `aud` tương đương.

Tệp `SecurityConfig.java` đặt trong package ứng dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Cách đọc mã:

- Chain đầu tiên chỉ xử lý `/api/**`, không dùng session; access token của API được kiểm tra bằng JWT. Scope `reports.read` được ánh xạ mặc định thành authority `SCOPE_reports.read` trong OAuth 2.0 Resource Server. API **vẫn phải kiểm tra quyền dữ liệu** trước khi trả bản ghi.
- Chain thứ hai phục vụ web browser, kích hoạt OIDC login khi có `openid` scope và client hợp lệ. Cookie/session của web được quản lý theo cơ chế Spring Security. **Không tắt CSRF cho toàn bộ web**; ví dụ chỉ tắt tại chain API stateless nhận bearer token từ header, không dùng cookie để xác thực.
- `permitAll()` cho health/public là lựa chọn chính sách ứng dụng, không phải quyền IdP áp đặt. Route API và route web cần được sắp xếp filter chain chặt chẽ; tránh cấu hình mặc định vô tình mở `anyRequest`.

Đối với SAML, dùng `saml2Login()` và metadata/chứng thư của IdP thay cho luồng OIDC. Đối với access token opaque, dùng cấu hình `oauth2ResourceServer(o -> o.opaqueToken(...))` và introspection thích hợp. Không tráo đổi các cơ chế này nếu token/đối tác không hỗ trợ.

## 11. Ví dụ thuần Java 17: quyền nghiệp vụ vẫn thuộc ứng dụng

Ví dụ sau **độc lập, chạy được bằng JDK 17** để chứng minh khác biệt giữa “đã biết danh tính” và “được đọc hóa đơn”. Nó không xác minh JWT; giả định định danh đã được Spring Security xác thực và backend ánh xạ sang tài khoản nội bộ đáng tin.

Tệp `PolicyDemo.java`:

```java
import java.util.Set;

public class PolicyDemo {
    record ExternalIdentity(String issuer, String subject) {}
    record Actor(
        ExternalIdentity identity,
        String internalUserId,
        String tenantId,
        Set<String> permissions
    ) {}
    record Invoice(String id, String ownerId, String tenantId) {}

    static boolean canRead(Actor actor, Invoice invoice) {
        return actor.permissions().contains("invoice:read")
            && actor.tenantId().equals(invoice.tenantId())
            && actor.internalUserId().equals(invoice.ownerId());
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            new ExternalIdentity("https://login.example.test", "alice-123"),
            "user-17",
            "tenant-A",
            Set.of("invoice:read")
        );

        Invoice ownInvoice = new Invoice("A-001", "user-17", "tenant-A");
        Invoice otherTenant = new Invoice("B-002", "user-17", "tenant-B");
        Invoice otherOwner = new Invoice("A-003", "user-99", "tenant-A");

        System.out.println("own=" + canRead(alice, ownInvoice));
        System.out.println("otherTenant=" + canRead(alice, otherTenant));
        System.out.println("otherOwner=" + canRead(alice, otherOwner));
    }
}
```

Lệnh:

```bash
javac PolicyDemo.java
java PolicyDemo
```

Kết quả chính xác:

```text
own=true
otherTenant=false
otherOwner=false
```

Trong ứng dụng thật, quy tắc có thể phức tạp hơn (cộng tác viên, phòng ban, quyền duyệt theo hạn mức, trạng thái hóa đơn). Nơi quyết định phải là service/repository có dữ liệu thật và được gọi ở mọi đường truy cập tới tài nguyên. **Không chấp nhận `tenantId` hoặc `internalUserId` người gọi tự gửi làm bằng chứng quyền**. Đầu vào tin cậy phải được dựng từ principal đã xác minh và dữ liệu membership bên server.

## 12. Phân biệt scope, role và quyền trên đối tượng

- **Scope OAuth 2.0** mô tả phạm vi access token được cấp, ví dụ `reports.read`. Scope thường gắn với client, consent và token; không nhất thiết là vai trò nhân viên.
- **Authority trong Spring Security** là chuỗi quyền dùng bởi các luật như `hasAuthority`. Resource Server JWT mặc định ánh xạ `scope`/`scp` thành `SCOPE_...`. Các claim `groups`/`roles` tùy nhà cung cấp phải được ánh xạ có chủ đích (ví dụ bằng `JwtAuthenticationConverter` hoặc `GrantedAuthoritiesMapper` trong luồng phù hợp).
- **Role nghiệp vụ** là khái niệm riêng của ứng dụng, ví dụ `ACCOUNTANT`, `PAYMENT_APPROVER`, có thể lấy từ DB hoặc đồng bộ có kiểm soát.
- **Permission theo đối tượng** xét quyền đối với `invoiceId`, `projectId`, `tenantId`, trạng thái và sở hữu; đây là điều kiện cần kiểm tra dù endpoint đã yêu cầu scope/role.

Ví dụ: request có `SCOPE_invoice.read` mới đủ để **vào luồng đọc hóa đơn**; để nhận hóa đơn 42, service vẫn cần chứng minh hóa đơn đó thuộc tenant người dùng và chính sách cấp quyền đọc cho người dùng ấy.

## 13. Lỗi thường gặp và cách xử lý

1. **“Đăng nhập được nghĩa là thấy tất cả dữ liệu”.** Sai: kiểm soát đối tượng ở nghiệp vụ và kiểm tra tenant ở server; không tin ID do client cung cấp.
2. **Gửi ID token đến API thay cho access token.** Sai mục đích token: API chỉ nhận access token dành cho API, có audience/issuer phù hợp.
3. **Chỉ decode JWT mà không verify.** Có thể bị giả mạo claim: dùng JWT decoder/verifier và cấu hình đủ issuer, audience, thời gian, thuật toán tin cậy.
4. **Tin bất kỳ issuer hoặc JWKS lấy từ token không kiểm soát.** Chỉ dùng danh sách IdP được cấu hình, không để người gửi token quyết định nguồn khóa đáng tin.
5. **Cho rằng `scope=admin` có nghĩa là superuser của mọi tenant.** Nghĩa scope phải được thỏa thuận; quyền dữ liệu vẫn do ứng dụng kiểm tra.
6. **Ánh xạ email làm khóa định danh cố định.** Email thay đổi/tái cấp; dùng ID ổn định với issuer và cơ chế liên kết tài khoản được kiểm chứng.
7. **Để chỉ gateway kiểm tra token rồi tin mọi request nội bộ.** API phải có ranh giới tin cậy rõ; kiểm tra access token/identity đáng tin và quyền nghiệp vụ tại nơi thực thi.
8. **Tắt CSRF cho toàn ứng dụng vì API dùng JWT.** Phải tách trường hợp cookie/session của browser với stateless bearer API; giữ CSRF cho luồng browser cần thiết.
9. **Tin rằng logout tại ứng dụng đã thu hồi ngay mọi token/phiên IdP.** Thiết kế cả local session, SSO logout và chính sách TTL/revocation; hành vi tùy IdP và giao thức.
10. **Tin rằng IdP khóa tài khoản là mọi JWT chưa hết hạn biến mất.** Kiểm soát vòng đời bằng token TTL, introspection/revocation khi cần, và kiểm tra trạng thái quyền nội bộ tại thời điểm truy cập.
11. **Quên reverse proxy/redirect URI và khóa xoay vòng.** Kiểm tra HTTPS, forwarded headers đáng tin, redirect URI đúng tuyệt đối, discovery/JWKS và theo dõi lỗi token validation.
12. **Ghi token vào log.** Giữ dấu vết `issuer`, subject được bảo vệ/mã hóa khi phù hợp, request ID, quyết định và lý do; không log bearer token, refresh token hay secret.

## 14. Tình huống kiểm tra thiết kế

| Tình huống | Kết quả kỳ vọng | Lớp chịu trách nhiệm chính |
| --- | --- | --- |
| Chưa đăng nhập vào trang web bảo vệ | Redirect đến IdP hoặc điểm đăng nhập được cấu hình | Spring Security web + IdP |
| Người dùng nhập sai mật khẩu/MFA | IdP từ chối xác thực | IdP |
| API nhận JWT hết hạn hoặc chữ ký không hợp lệ | Từ chối xác thực, thường HTTP 401 | Spring Security Resource Server |
| API nhận token từ issuer lạ hoặc audience dành cho API khác | Từ chối xác thực nếu đã cấu hình validator đúng | Spring Security Resource Server |
| Token hợp lệ nhưng thiếu scope cho endpoint | Từ chối phân quyền, thường HTTP 403 | Spring Security |
| Scope đúng, hóa đơn thuộc tenant khác | Từ chối hoặc che giấu sự tồn tại tài nguyên theo chính sách | Service nghiệp vụ |
| Người dùng đã rời phòng ban nhưng token vẫn còn hạn | Quyền nội bộ phải được cập nhật/kiểm tra; hiệu lực thu hồi token phụ thuộc thiết kế | IdP + đồng bộ membership + nghiệp vụ |
| IdP tạm không truy cập được | Đăng nhập/token introspection có thể thất bại; JWT đã hợp lệ có thể còn dùng theo chính sách cache và TTL | Vận hành IdP + cấu hình client/API |
| Người dùng bấm logout trong portal | Hủy phiên portal; muốn hủy SSO/liên thông phải tích hợp logout tương ứng | Spring Security web + IdP + ứng dụng |

HTTP 401 và 403 phụ thuộc loại request và entry point: **API bearer** thường dùng 401 cho chưa được xác thực/token không hợp lệ và 403 cho đã xác thực nhưng thiếu quyền. **Ứng dụng browser** có thể redirect đến trang đăng nhập thay vì trả trực tiếp 401.

## 15. Các nguyên tắc triển khai thực tế

1. **Thống nhất hợp đồng trust:** issuer, protocol OIDC/SAML, client ID, redirect/ACS URL, audience, scope, thuật toán/chứng thư, rotate keys, metadata và owner của mỗi cấu hình.
2. **Tách ba lớp chính sách:** (a) xác thực và MFA tại IdP; (b) endpoint/method tại Spring Security; (c) quyền đối tượng/tenant tại nghiệp vụ.
3. **Dùng danh tính ổn định, có namespace:** ánh xạ `issuer + subject`, tránh gộp hai tài khoản từ hai nhà cung cấp chỉ vì trùng email.
4. **Hạn chế token và dữ liệu danh tính:** scope nhỏ nhất, TTL phù hợp, không lộ token trên URL/log, quản lý secret an toàn, kiểm tra audience tại API.
5. **Xác định hành vi khi thu hồi quyền:** IdP deprovision, JIT provisioning, group sync, revoke session, TTL access token, kiểm tra membership tại API.
6. **Kiểm thử bảo mật theo cả hai chiều:** token không hợp lệ/thiếu scope và token hợp lệ nhưng không có quyền nghiệp vụ. Đây là hai loại test khác nhau.
7. **Quan sát theo đúng lớp:** lỗi mật khẩu/MFA ở IdP; lỗi issuer/signature/audience ở Resource Server; lỗi quyền hóa đơn ở application service.
8. **Đặt kiểm soát gần dữ liệu:** controller/method security hữu ích nhưng không thay thế chính sách khi service được gọi từ batch job, event consumer hoặc API khác.

## 16. Câu hỏi tự kiểm tra

- Nếu IdP xác thực thành công nhưng người dùng cố đọc dữ liệu tenant khác, lớp nào phải từ chối? **Hệ thống nghiệp vụ**, sau khi Spring Security đã xác thực token và áp dụng luật endpoint.
- Spring Security mặc định tạo Authorization Server/IdP khi bật `oauth2Login()`? **Không**; ứng dụng trở thành client/relying party của IdP đã cấu hình.
- `ID token` và `access token` dùng như nhau được không? **Không**; đối tượng nhận và mục đích khác nhau.
- Vì sao `sub` nên đi cùng `iss`? **Vì subject chỉ có ý nghĩa trong không gian của nhà phát hành**; hai IdP có thể cấp cùng một giá trị subject cho hai người khác nhau.
- Một JWT còn hạn nhưng người dùng đã bị xóa quyền nghiệp vụ có luôn được truy cập không? **Không**; API phải kiểm tra trạng thái/quyền nội bộ theo chính sách; việc thu hồi JWT tức thời cần thiết kế riêng.

## Tài liệu đối chiếu

- Spring Security, OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security, Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security, Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security, SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Authorization Server, Overview: https://docs.spring.io/spring-authorization-server/reference/overview.html

**Ghi nhớ:** Liên kết danh tính giúp các ứng dụng **tin vào kết quả xác thực có kiểm chứng**. Spring Security hiện thực bảo mật request tại ứng dụng/API; IdP chịu trách nhiệm xác lập và phát hành thông tin danh tính/token; hệ thống nghiệp vụ sở hữu quyết định cuối cùng trên dữ liệu và hành động của mình.