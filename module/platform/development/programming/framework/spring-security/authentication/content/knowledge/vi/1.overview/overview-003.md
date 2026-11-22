# Người dùng, tài khoản dịch vụ và nhà cung cấp danh tính trong Spring Security

> **Ngữ cảnh:** Spring Security — Authentication / Tổng quan. Bài này giải thích *ai hoặc cái gì đang được xác thực*, *ai cấp bằng chứng danh tính* và *ứng dụng Java nên diễn giải danh tính đó như thế nào*. Các ví dụ OAuth 2.0/OIDC giả định ứng dụng Spring Boot 3.x, Spring Security 6.x trở lên và Java 17+; cấu hình minh họa cần một Identity Provider (IdP) thực tế để cấp token.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt **người dùng (human user)**, **tài khoản dịch vụ (service account / workload identity)** và **nhà cung cấp danh tính (Identity Provider — IdP)**.
2. Phân biệt chủ thể (subject/principal), tài khoản, thông tin xác thực (credential), phiên đăng nhập, access token, ID token và quyền truy cập.
3. Trình bày luồng đăng nhập của người dùng và luồng máy gọi máy bằng `client_credentials`; hiểu khi nào có hoặc không có người dùng ở phía sau yêu cầu.
4. Nhận biết `Authentication`, `SecurityContext`, `AuthenticationManager`, `AuthenticationProvider` và `GrantedAuthority` trong Spring Security.
5. Chọn ranh giới tin cậy và kiểm tra quyền phù hợp; tránh nhầm danh tính đã xác thực với quyền đã được phép.

## 2. Ba khái niệm: ai, tài khoản nào, ai xác nhận?

| Thành phần | Bản chất và ví dụ | Thường sở hữu credential gì? | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Người dùng** | Một cá nhân: nhân viên Lan, khách hàng Minh, quản trị viên vận hành | Mật khẩu + MFA, passkey, khóa bảo mật, phiên đăng nhập; hoặc được IdP xác thực | Một người có thể có nhiều tài khoản; tài khoản bị khóa không có nghĩa con người không tồn tại |
| **Tài khoản dịch vụ** | Danh tính dành cho ứng dụng, job, worker, workload: `svc-invoice-export`, CI job | Client secret, private key, chứng chỉ, identity từ nền tảng, token ngắn hạn | Không đại diện mặc định cho một người; cần chủ sở hữu vận hành, quyền tối thiểu và vòng đời riêng |
| **IdP** | Hệ thống xác minh và quản lý danh tính, ví dụ IdP doanh nghiệp hoặc OpenID Provider | Giữ hồ sơ người dùng, chính sách đăng nhập, khóa ký và/hoặc hệ thống xác thực | IdP là bên xác nhận danh tính; API phải tự kiểm tra token và quyết định quyền tài nguyên |

**Danh tính (identity)** là tập thông tin nhận diện một chủ thể. **Chủ thể (subject/principal)** là thực thể mà cơ chế bảo mật đang nói đến; có thể là người hoặc workload. **Tài khoản (account)** là bản ghi dùng để quản lý chủ thể, credential và trạng thái. **Credential** là bằng chứng để xác thực; **token** là thông điệp do bên tin cậy phát hành, mang phạm vi/thông tin và thời hạn sử dụng. Một token thường là bearer credential: ai cầm token hợp lệ có thể sử dụng cho đến khi nó hết hiệu lực hoặc bị chặn theo cơ chế áp dụng.

Phân biệt hai câu hỏi:
- **Authentication (xác thực):** “Yêu cầu này được gửi bởi chủ thể nào, với bằng chứng có đáng tin không?”
- **Authorization (phân quyền):** “Chủ thể ấy có được đọc báo cáo, sửa hồ sơ, gọi API hay thao tác trên đúng tenant này không?”

Đăng nhập thành công không tự động đồng nghĩa có mọi quyền. “Đã xác thực” và “được phép thực hiện hành động cụ thể” là hai quyết định khác nhau.

## 3. Người dùng: danh tính con người và vòng đời truy cập

Một ứng dụng có thể lưu người dùng cục bộ (ví dụ `UserDetailsService` tra cứu tên đăng nhập/mật khẩu đã băm) hoặc ủy quyền quá trình đăng nhập cho IdP. Với hệ thống doanh nghiệp, IdP thường hỗ trợ đăng nhập tập trung, MFA, chính sách thiết bị và thu hồi quyền khi nhân viên nghỉ việc. Ứng dụng vẫn có thể cần dữ liệu nghiệp vụ riêng: khách hàng thuộc tổ chức nào, trạng thái tài khoản trong sản phẩm, đơn hàng được phép thấy.

Ví dụ tên người dùng “lan” có thể xuất hiện trong nhiều hệ thống. Khi ghép danh tính từ nguồn bên ngoài, khóa bền vững thường là cặp **`(issuer, subject)`**: `iss` cho biết bên phát hành và `sub` nhận diện subject trong phạm vi issuer đó. Đừng mặc định email, tên hiển thị, số điện thoại hay username là khóa định danh toàn cục bất biến; chúng có thể thay đổi, trùng hoặc chưa được xác thực.

Vòng đời nên bao gồm: tạo tài khoản và xác minh → đăng nhập/MFA → cấp quyền theo công việc → thay đổi vai trò → vô hiệu hóa/khóa → xóa hoặc lưu trữ theo chính sách. Một phiên đăng nhập web có cookie và thời hạn riêng; không đồng nhất phiên với access token. Nếu người dùng rời tổ chức, cần xem cả phiên hiện hữu, token còn hạn và quyền truy cập ở hệ thống phụ thuộc.

**Tình huống:** Lan đăng nhập bằng OIDC và mở báo cáo tài chính. IdP chứng thực “đây là Lan”; API báo cáo kiểm tra tiếp Lan có quyền xem **báo cáo đó trong tenant đó** hay không. Cả hai kiểm tra đều cần thiết.

## 4. Tài khoản dịch vụ: danh tính của phần mềm, không phải “một user đặc biệt” theo mặc định

Một batch job chạy lúc 02:00 không có con người nhập mật khẩu. Job vẫn cần danh tính riêng để hệ thống nhận diện và truy vết. Tài khoản dịch vụ giúp quản trị câu hỏi: “Workload nào gọi API, ai chịu trách nhiệm vận hành, nó được làm gì, credential sẽ luân chuyển khi nào?”

**Các mô hình thường gặp:**
- **Service account tại hệ thống nội bộ:** bản ghi như `svc-report-job` trong kho danh tính; có thể dùng mTLS/chứng chỉ hoặc cơ chế nội bộ. Không nhất thiết là tài khoản người dùng có thể đăng nhập giao diện.
- **OAuth 2.0 confidential client:** ứng dụng được đăng ký với Authorization Server bằng `client_id` và cách xác thực client (secret, private key JWT, mTLS…). Khi dùng `client_credentials`, client tự xin access token cho chính nó, **không có người dùng cuối** trong luồng.
- **Workload identity / federation:** môi trường chạy (ví dụ nền tảng cloud hoặc orchestrator) cấp một danh tính có thể kiểm chứng, giảm nhu cầu cất secret dài hạn. “Không có secret tĩnh” không có nghĩa bỏ xác thực.

`client_id` là định danh của OAuth client, còn `sub` của access token phụ thuộc quy ước bên phát hành. Không suy diễn rằng hai giá trị luôn bằng nhau. Tùy nhà cung cấp, token có thể chứa các claim riêng để chỉ client, workload, bên được ủy quyền hoặc loại grant; **chỉ dùng các claim đã được xác minh và có hợp đồng rõ ràng với IdP**.

### Luồng máy gọi máy bằng OAuth 2.0 client credentials

~~~mermaid
sequenceDiagram
    participant Job as Batch job
    participant AS as Authorization Server / IdP
    participant API as Resource Server (Spring Security)
    Job->>AS: Xác thực client + grant_type=client_credentials
    AS-->>Job: Access token (giới hạn scope, audience, expiry)
    Job->>API: GET /api/reports + Bearer access token
    API->>API: Kiểm tra chữ ký/issuer/audience/thời gian
    API->>API: Kiểm tra scope và quyền tài nguyên
    API-->>Job: 200 hoặc 401/403
~~~

Vì không có người dùng cuối trong `client_credentials`, API không được giả định token ấy mang sự đồng ý hoặc quyền của Lan. Nếu một tiến trình thay mặt Lan thực hiện yêu cầu, đó là **ủy quyền có ngữ cảnh người dùng** (delegation/on-behalf-of hoặc cơ chế được thiết kế tương đương), khác với token chỉ đại diện cho workload. Việc job ghi `createdBy = "admin"` hay tự tạo “user giả” không biến nó thành quyền của quản trị viên.

**Quy tắc vận hành:** tạo danh tính riêng cho từng dịch vụ/môi trường hoặc mục đích tin cậy; gán scope tối thiểu; tránh chia sẻ secret giữa các workload; lưu secret trong secret manager hoặc dùng danh tính workload; luân chuyển và thu hồi credential; ghi audit theo service identity, client và tác vụ; khóa tài khoản hoặc thu hồi quyền khi job không còn tồn tại. Không nhúng secret vào mã nguồn, nhật ký hoặc tham số dòng lệnh dễ bị ghi lại.

## 5. Nhà cung cấp danh tính (IdP), Authorization Server, OIDC Provider

Ba tên gọi liên quan nhưng không đồng nghĩa hoàn toàn:

- **Identity Provider (IdP):** xác minh danh tính, quản lý hoặc liên kết tài khoản, thi hành MFA và chính sách đăng nhập. Có thể dùng OIDC, SAML hoặc cơ chế khác.
- **OAuth 2.0 Authorization Server:** xác thực/ủy quyền theo giao thức, phát hành access token cho OAuth client theo grant và chính sách; không phải mọi hệ thống OAuth đều là IdP cho người dùng.
- **OpenID Provider (OP):** hệ thống hỗ trợ OpenID Connect trên OAuth 2.0, cho phép ứng dụng xác minh danh tính người dùng và nhận `ID token`. Một sản phẩm có thể đảm nhận cả ba vai trò.

**OAuth 2.0 chủ yếu nói về ủy quyền truy cập tài nguyên; OIDC thêm lớp xác thực danh tính người dùng.** Trong luồng web “Đăng nhập với IdP”, ứng dụng thường dùng Authorization Code với cơ chế bảo vệ phù hợp như PKCE, nhận ID token để xác thực đăng nhập phía client và access token để gọi API được cấp quyền. **ID token không phải access token**: API không nên chấp nhận ID token thay cho access token. Resource Server phải kiểm tra token được phát hành đúng cho mình.

IdP có thể liên kết tới kho người dùng/LDAP/AD hoặc một IdP khác; kho danh bạ không tự động là hệ thống phát hành OAuth access token. Liên kết đa IdP phải xác định rõ issuer nào được tin cậy, cách ánh xạ tài khoản và quyền; không gộp hai chủ thể chỉ vì email giống nhau.

### Hai đường đi thường gặp của người dùng

1. **Đăng nhập cục bộ:** browser gửi credential qua kênh bảo mật → ứng dụng/Spring Security đối chiếu với nguồn người dùng → tạo `Authentication` đã xác thực → duy trì phiên theo thiết kế. Quy trình xác thực phụ thuộc cấu hình; mật khẩu phải được lưu theo cơ chế băm mật khẩu thích hợp, không lưu bản rõ.
2. **Đăng nhập OIDC:** browser được chuyển đến IdP → IdP xác thực người dùng (có thể MFA) → ứng dụng nhận authorization code, đổi token tại token endpoint và xác minh kết quả → ứng dụng duy trì phiên đăng nhập của mình nếu dùng mô hình web session.

Không tự chuyển access token của một issuer sang issuer khác, bỏ qua audience, hoặc xem việc “decode được JWT” là xác thực hợp lệ. Decode Base64 chỉ đọc dữ liệu; **xác minh chữ ký và các điều kiện token** mới là bước tin cậy.

## 6. Bảng chọn mô hình xác thực

| Tình huống | Chủ thể cần nhận diện | Cách tiếp cận phù hợp | Chỗ quyết định quyền |
| --- | --- | --- | --- |
| Nhân viên đăng nhập ứng dụng web | Người dùng cụ thể | OIDC login / SSO, phiên web phù hợp | Ứng dụng + API, dựa trên vai trò và tài nguyên |
| Người dùng gọi API qua ứng dụng có ủy quyền | Người dùng và ứng dụng liên quan | Authorization Code + PKCE, access token dành cho API | API kiểm tra scope và quyền trên dữ liệu |
| Scheduler gọi API nội bộ | Workload hoặc OAuth client | Client Credentials, workload identity hoặc mTLS | API kiểm tra service identity, scope, audience và policy |
| API nhận JWT bearer token | Subject trong access token | OAuth2 Resource Server của Spring Security | Authentication từ token và authorization trên endpoint/dữ liệu |
| Dịch vụ cần hành động *thay mặt người dùng* | Cả user context lẫn client | Delegation/token exchange theo IdP được hỗ trợ | API kiểm tra cả quyền ủy quyền và quyền tài nguyên |

**Ví dụ giới hạn quyền:** `svc-export` chỉ cần `reports.read`; đừng cấp `users.admin`. Ngược lại, Lan có quyền xem một số báo cáo không đồng nghĩa job dịch vụ sở hữu quyền đó. Quyền tối thiểu phải tính cả *tenant, tài nguyên, hành động, thời gian* nếu nghiệp vụ cần.

## 7. Spring Security thấy “ai đang gọi” như thế nào?

Trong ứng dụng **Servlet** của Spring Security, một yêu cầu HTTP đi qua chuỗi security filter. Theo cơ chế xác thực đã chọn, filter nhận credential/token, chuyển qua thành phần xác thực phù hợp và tạo đối tượng `Authentication`. Khi xác thực thành công, thông tin được đặt trong `SecurityContext` để phần còn lại của request có thể lấy ra. `SecurityContextHolder` mặc định dùng dữ liệu theo thread, vì vậy không tự giả định context lan sang thread nền hoặc tác vụ bất đồng bộ.

Các thành phần cốt lõi:

| Thành phần | Vai trò |
| --- | --- |
| `Authentication` | Chứa `principal`, `credentials` (nếu còn), `authorities` và trạng thái xác thực; cũng có thể là yêu cầu xác thực trước khi được xác nhận |
| `AuthenticationManager` | Giao diện điều phối yêu cầu xác thực; `ProviderManager` là cách triển khai phổ biến |
| `AuthenticationProvider` | Xác thực một loại credential/token; ví dụ provider cho username/password hoặc JWT |
| `SecurityContext` / `SecurityContextHolder` | Lưu thông tin xác thực trong ngữ cảnh xử lý hiện tại |
| `GrantedAuthority` | Quyền/role/scope đã ánh xạ để Spring Security dùng khi phân quyền |
| `SecurityFilterChain` | Định nghĩa đường đi và quy tắc bảo mật của HTTP request |

**Hình dạng principal thay đổi theo cơ chế đăng nhập:** với username/password có thể là `UserDetails`; với OAuth2/OIDC Login có thể là `OAuth2User`/`OidcUser`; với JWT Resource Server mặc định principal là `Jwt` và `Authentication` thường là `JwtAuthenticationToken`. **Đừng cast tất cả principal sang `UserDetails`** hoặc cho rằng `authentication.getName()` luôn là email. Với JWT Resource Server, name mặc định thường lấy claim `sub`.

Roles và scopes không tự đồng nghĩa. `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo quy ước mặc định; JWT Resource Server mặc định ánh xạ scope thành authority dạng `SCOPE_reports.read`. Chỉ tạo ánh xạ từ claim sang quyền ứng dụng sau khi định nghĩa rõ issuer tin cậy, ý nghĩa claim, tenant và mức truy cập.

### Ví dụ tích hợp A — API nhận access token từ IdP

Ví dụ này dành cho **một Spring Boot Servlet API đã có** `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`. Nó là cấu hình tích hợp, **không phải chương trình Java SE độc lập**. Thay issuer/audience giả bằng giá trị thực của Authorization Server và API; đăng ký client, scope, khóa ký ở IdP.

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant
          audiences: https://api.example.test
```

`src/main/java/example/demo/ApiSecurityConfig.java`:

```java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(requests -> requests
                .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
```

`src/main/java/example/demo/IdentityController.java`:

```java
package example.demo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        Object principal = authentication.getPrincipal();
        String subject = principal instanceof Jwt jwt
                ? jwt.getSubject()
                : authentication.getName();

        return Map.of(
                "subject", subject,
                "authenticationType", authentication.getClass().getSimpleName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "Report visible";
    }
}
```

**Cách kiểm tra (với IdP và token thực tế):**
- `GET /api/me` không có access token hợp lệ → thông thường **401 Unauthorized**.
- Bearer access token hợp lệ, đúng issuer/audience nhưng không có `reports.read` → `GET /api/reports` bị **403 Forbidden**.
- Token hợp lệ có scope `reports.read`, được Spring ánh xạ thành `SCOPE_reports.read` → `GET /api/reports` trả body `Report visible` (200).
- `/api/me` minh họa `Authentication`; trường `authenticationType` phụ thuộc cách Spring xác thực. Thứ tự các trường JSON không phải hợp đồng cố định.

Cấu hình ở trên chỉ minh họa các đường **GET**. Với API có POST/PUT/DELETE, cần thiết kế CSRF, session, CORS và các chính sách khác theo mô hình client thực tế. Trong hệ thống nhiều tenant, `hasAuthority("SCOPE_reports.read")` chỉ là điều kiện bước đầu: lớp nghiệp vụ còn phải kiểm tra token/chủ thể có quyền truy cập *báo cáo cụ thể* thuộc tenant nào.

Mặc định Resource Server JWT sẽ xác minh chữ ký, issuer, thời gian hiệu lực và ánh xạ scope. Cấu hình `audiences` thêm kiểm tra audience dành cho API. Với opaque token, dùng cơ chế introspection phù hợp thay vì tự xử lý JWT. Cách IdP thể hiện service identity trong claim không có quy ước chung đủ để đoán qua một trường duy nhất.

### Ví dụ tích hợp B — Một dịch vụ xin token bằng client_credentials

Đây là **cấu hình của dịch vụ gọi API**, khác với cấu hình Resource Server nhận token ở ví dụ A. Ứng dụng caller dùng `spring-boot-starter-oauth2-client` và đăng ký OAuth client với Authorization Server. `REPORTS_CLIENT_SECRET` được cấp qua môi trường/secret manager; không commit giá trị thật.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-job:
            provider: internal-as
            client-id: report-batch-job
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: reports.read
        provider:
          internal-as:
            token-uri: https://idp.example.test/oauth2/token
```

Trong cấu hình thật, giá trị `client-secret` là biểu thức thuộc tính Spring `${REPORTS_CLIENT_SECRET}`. Một `OAuth2AuthorizedClientManager` được cấu hình phù hợp sẽ lấy, lưu và sử dụng access token theo grant `client_credentials`; job chạy nền thường cần manager dựa trên `OAuth2AuthorizedClientService`, không tự dựa vào `HttpServletRequest` của một người dùng. Khi gọi API, truyền access token trong header `Authorization: Bearer ...` qua HTTPS. **Không truyền ID token** ở đây. Đừng tự viết cơ chế lấy token/refresh/secret-storage nếu framework và IdP đã cung cấp luồng phù hợp.

Ví dụ trên nêu cấu hình, **không tạo được token khi chưa có IdP, đăng ký client, credential và chính sách scope thực tế**. Việc AS có cấp scope cụ thể hay không và claim token trông thế nào phụ thuộc cấu hình của AS.

### Ví dụ tích hợp C — Đăng nhập người dùng với OIDC

Ứng dụng web thông thường thêm `spring-boot-starter-oauth2-client`, đăng ký client cho Authorization Code và khai báo issuer của OIDC Provider. Với cấu hình đăng ký hợp lệ, filter chain có thể bật:

```java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
```

Đây là **đoạn phương thức tích hợp vào một lớp `@Configuration`**, không phải tệp Java chạy độc lập; cần các import và cấu hình client/redirect URI tương ứng. Trong handler dành cho người dùng đã đăng nhập, có thể nhận `@AuthenticationPrincipal OidcUser` nếu principal thực sự thuộc luồng OIDC. Luồng này tạo ngữ cảnh đăng nhập của **người dùng**, khác với `client_credentials` của batch job. Với ứng dụng có nhiều filter chain, phải xác định phạm vi URL và thứ tự khớp rõ ràng; các ví dụ A và C là **hai lựa chọn độc lập**, không copy hai bean bắt mọi request vào cùng một app.

## 8. Ví dụ Java 17 độc lập: cùng quyền, khác loại chủ thể

Ví dụ Java SE dưới đây **chạy được không cần Spring**, chỉ diễn tả logic nghiệp vụ sau khi một tầng xác thực đáng tin đã nhận diện principal và cấp permission. Nó không thực hiện xác thực hay xác minh JWT, vì thế không thay thế Spring Security.

Lưu đúng tên tệp `IdentityDecisionDemo.java`:

```java
import java.util.Set;

public class IdentityDecisionDemo {
    enum Kind { HUMAN, SERVICE }

    record Caller(String subject, Kind kind, Set<String> permissions) {}

    static boolean canReadReports(Caller caller) {
        return caller.permissions().contains("reports.read");
    }

    public static void main(String[] args) {
        Caller human = new Caller(
                "user:lan", Kind.HUMAN, Set.of("reports.read"));
        Caller service = new Caller(
                "service:nightly-export", Kind.SERVICE, Set.of("reports.read"));
        Caller guest = new Caller(
                "user:guest", Kind.HUMAN, Set.of());

        System.out.println("human=" + canReadReports(human));
        System.out.println("service=" + canReadReports(service));
        System.out.println("guest=" + canReadReports(guest));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac IdentityDecisionDemo.java
java IdentityDecisionDemo
```

Stdout chính xác:

```text
human=true
service=true
guest=false
```

Giải thích: **loại chủ thể** cho biết ai đang hoạt động; **permission** mới quyết định hành động “đọc báo cáo” trong ví dụ. Ngoài thực tế, không được tin một `Caller` tự do gửi từ client: phải tạo nó từ `Authentication`/token đã xác minh, rồi kiểm tra thêm quyền trên tenant và bản ghi. Một hệ thống có thể cấm riêng tài khoản dịch vụ dùng một endpoint ngay cả khi cùng scope; đó là **chính sách nghiệp vụ bổ sung** được thiết kế rõ ràng.

## 9. Các claim và ranh giới tin cậy cần nhớ

| Trường/khái niệm | Câu hỏi cần trả lời | Điều không được suy diễn |
| --- | --- | --- |
| `iss` (issuer) | Ai phát hành token? API có tin issuer này không? | JWT có chữ ký hợp lệ từ **bất kỳ** issuer nào đều được chấp nhận |
| `sub` (subject) | Token gắn với chủ thể nào trong phạm vi issuer? | `sub` là email hoặc luôn là `client_id` |
| `aud` (audience) | Token dành cho dịch vụ/API nào? | Token hợp lệ cho App A sẽ được dùng hợp lệ ở API B |
| `exp`, `nbf` | Token đã hết hạn hoặc chưa đến thời điểm hợp lệ? | Token không có giới hạn thời gian hoặc không cần cơ chế thu hồi |
| `scope` / `scp` | AS cấp phạm vi truy cập nào? | Scope tự động thay cho mọi kiểm tra tài nguyên và tenant |
| `client_id` / claim client liên quan | Client/workload nào tham gia luồng? | Client giống người dùng cuối hoặc claim luôn có tên/ý nghĩa giống nhau |
| `Authentication#getAuthorities()` | Spring đã ánh xạ những authority nào? | Mọi role từ một IdP đều được tin như role nội bộ mà không có quy tắc ánh xạ |

Một API cần đặt **ranh giới tin cậy tại nơi nhận request**: validate token đúng định dạng, chữ ký hoặc introspection, issuer, audience, expiry, trạng thái và các quy tắc bổ sung; sau đó phân quyền theo endpoint, bản ghi và tenant. JWT ký hợp lệ vẫn có thể bị từ chối vì sai audience/scope. Token bearer bị đánh cắp vẫn có thể được dùng trong cửa sổ hiệu lực: dùng HTTPS, token thời hạn ngắn, bảo vệ lưu trữ và cơ chế phản ứng sự cố.

**Audit hữu ích** thường ghi request/correlation ID, issuer, subject hoặc client identifier đã xác minh, hành động, tài nguyên, quyết định cho phép/từ chối. Tránh ghi raw access token, ID token, mật khẩu, client secret và dữ liệu nhạy cảm trong log.

## 10. Các lỗi thực tế thường gặp

1. **Coi service account như “admin user dùng chung”.** Mất truy vết và mở rộng quyền quá mức. Tạo danh tính workload riêng, có owner, scope, môi trường và chính sách luân chuyển.
2. **Chỉ decode JWT rồi tin claim.** Phải xác minh token và issuer/audience/time; không tin claim do request body/header do client tự gán.
3. **Dùng ID token để gọi API.** ID token xác minh đăng nhập cho OIDC client; Resource Server kiểm tra access token được cấp cho nó.
4. **Nhầm `client_credentials` với đăng nhập người dùng.** Grant này không có người dùng cuối; không gán tác vụ của service thành tác vụ được user ủy quyền nếu chưa có bằng chứng delegation.
5. **Dùng email làm khóa người dùng toàn cục.** Với federation nên liên kết theo subject và issuer, kèm quy trình merge/link tài khoản được kiểm soát.
6. **Tin mọi group/role từ IdP thành quyền quản trị.** Thiết lập mapping rõ ràng, giới hạn issuer đáng tin và kiểm tra quyền dữ liệu ở API.
7. **Xem `authenticated()` là đủ.** Điều này chỉ chứng thực request có Authentication hợp lệ theo cấu hình; endpoint nhạy cảm vẫn cần scope/role và kiểm tra ownership.
8. **Không thu hồi/luân chuyển service credential.** Credential tồn tại vô hạn là rủi ro lớn; dùng thời hạn ngắn, secret manager hoặc workload identity.
9. **Tin rằng logout luôn vô hiệu ngay mọi access token JWT.** Thực tế còn phụ thuộc thời hạn token, revocation/introspection, session và chính sách của IdP/Resource Server.
10. **Lấy SecurityContext từ thread khác theo giả định.** Với job/scheduler hoặc async execution, dùng cách truyền ngữ cảnh phù hợp và chủ động định danh workload; không tái sử dụng ngẫu nhiên context của request người dùng.

## 11. Tình huống kiểm tra hiểu biết

**Tình huống 1:** Lan đăng nhập SSO thành công nhưng nhận 403 khi gọi `/api/reports`. Điều này có mâu thuẫn không?  
**Trả lời:** Không. Lan đã xác thực thành công, nhưng API có thể thiếu `SCOPE_reports.read` hoặc thiếu quyền trên báo cáo/tenant đang được yêu cầu. Nếu token sai/hết hạn hoặc thiếu hẳn xác thực, mã thường gặp là 401.

**Tình huống 2:** Một batch job nhận access token qua `client_credentials`; token có `client_id=report-batch-job`. Có thể gán tất cả hành động cho người dùng “Lan” không?  
**Trả lời:** Không. Token này đại diện cho client/workload, trừ khi có cơ chế ủy quyền người dùng riêng được AS và API xác minh. Audit theo service identity và chủ sở hữu vận hành.

**Tình huống 3:** Hai IdP đều phát hành `sub=123`. Đó có phải một người?  
**Trả lời:** Không thể kết luận. `sub` có phạm vi theo issuer; phải xét cặp `(iss, sub)` và quy trình liên kết tài khoản.

**Tình huống 4:** Một JWT ký đúng nhưng `aud` là dịch vụ thanh toán; API báo cáo có nên chấp nhận không?  
**Trả lời:** Không. Token không được phát hành cho API báo cáo, dù chữ ký hợp lệ.

**Tình huống 5:** Người dùng có role nội bộ `ROLE_MANAGER`, workload có `SCOPE_reports.read`; cả hai cần xem cùng báo cáo. Có nên gộp role và scope một cách máy móc?  
**Trả lời:** Không. Cần chính sách rõ ràng xác định chủ thể nào có quyền đọc báo cáo nào. Role và scope là tín hiệu đầu vào; kiểm tra quyền tài nguyên/tenant vẫn thuộc ứng dụng.

## 12. Ghi nhớ khi thiết kế

- **Human user**: có người thật, đăng nhập và vòng đời tài khoản; IdP có thể đảm nhận chứng thực.
- **Service account/workload**: có danh tính riêng cho phần mềm; `client_credentials` không mang user context.
- **IdP/Authorization Server**: xác minh/chứng thực và có thể cấp token; **Resource Server** phải xác minh token và áp dụng chính sách truy cập của mình.
- Trong Spring Security, `Authentication` mô tả chủ thể đã xác thực và authorities; **`authenticated()` không thay thế kiểm tra quyền**.
- Luôn hỏi: **ai cấp bằng chứng? token dành cho ai? chủ thể là ai? hành động nào được phép trên tài nguyên nào?** Trả lời đủ bốn câu hỏi trước khi tin một request.

### Tài liệu tham khảo chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth 2.0 Client / Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
