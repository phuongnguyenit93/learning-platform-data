# 1.7. Phạm vi trách nhiệm giữa ứng dụng client và nhà cung cấp định danh

Trong ứng dụng Spring Boot sử dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, người dùng thường được chuyển đến một hệ thống đăng nhập tập trung, chẳng hạn Keycloak, Microsoft Entra ID, Okta hoặc một OpenID Provider khác. Sau khi đăng nhập, người dùng quay lại ứng dụng và sử dụng chức năng nghiệp vụ như bình thường.

Việc «đăng nhập qua IdP» không có nghĩa nhà cung cấp định danh chịu trách nhiệm cho toàn bộ bảo mật của ứng dụng. **Nhà cung cấp định danh xác thực người dùng và phát hành các thông tin/token theo giao thức; ứng dụng client phải bảo vệ luồng đăng nhập, thiết lập phiên của mình, xác định người dùng được làm gì và bảo vệ dữ liệu nghiệp vụ.** Nếu ứng dụng gọi một API độc lập, API đó còn có trách nhiệm kiểm tra quyền truy cập ở phía resource server.

Bài học này tập trung vào ranh giới trách nhiệm ấy: phần nào có thể giao cho IdP, phần nào Spring Security hỗ trợ, và phần nào đội phát triển ứng dụng vẫn phải thiết kế.

## 1. Các vai trò trong hệ thống

Ví dụ: một hệ thống quản lý đơn hàng có giao diện web viết bằng Spring Boot, dùng IdP của doanh nghiệp để đăng nhập và gọi API quản lý đơn hàng.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **End User** | Người dùng cuối muốn sử dụng ứng dụng. | Nhân viên đăng nhập để xem đơn hàng. |
| **User Agent** | Trình duyệt thực hiện các chuyển hướng giữa ứng dụng và IdP. | Chrome, Firefox. |
| **OAuth 2.0 Client / OIDC Relying Party (RP)** | Ứng dụng yêu cầu đăng nhập, tiếp nhận kết quả OIDC và quản lý phiên nghiệp vụ. | Ứng dụng Spring Boot cấu hình `oauth2Login`. |
| **Identity Provider (IdP) / OpenID Provider (OP)** | Hệ thống định danh xác thực người dùng, quản lý chính sách đăng nhập và phát hành ID Token. Trong OIDC, OP cũng thực hiện vai trò OAuth 2.0 Authorization Server. | Hệ thống SSO của công ty. |
| **Resource Server** | API tiếp nhận Access Token, kiểm tra token và kiểm soát quyền truy cập tài nguyên API. | API đơn hàng nhận `Authorization: Bearer ...`. |
| **Spring Security** | Thư viện triển khai những phần giao thức và cơ chế bảo mật đã cấu hình, ở phía client và/hoặc resource server. | Filter chain, OIDC login, lưu `SecurityContext`. |

Cần phân biệt hai từ thường xuất hiện cùng nhau:

- **Authentication (xác thực):** «Người đang đăng nhập là ai?» IdP thường là nơi quyết định việc kiểm tra mật khẩu, MFA, passkey hoặc phương thức đăng nhập khác.
- **Authorization (phân quyền):** «Người đó được làm gì đối với tài nguyên cụ thể?» IdP có thể cung cấp nhóm và thuộc tính hỗ trợ phân quyền, nhưng ứng dụng và API phải quyết định quyền đối với chức năng, dữ liệu của chính mình.

Một ứng dụng có thể đồng thời đóng nhiều vai trò. Chẳng hạn, Spring Boot vừa đăng nhập người dùng bằng `oauth2Login`, vừa có endpoint REST nhận bearer token bằng `oauth2ResourceServer`. Khi đó, phải thiết kế **hai luồng bảo mật khác nhau**; việc ứng dụng là OIDC Client không tự biến mọi API trong ứng dụng thành Resource Server an toàn.

## 2. Ranh giới trách nhiệm: ai sở hữu quyết định nào?

Bảng sau dùng trường hợp phổ biến: web application có backend Spring Boot, đăng nhập theo **Authorization Code Flow**, và gọi API dùng Access Token.

| Hạng mục | IdP / Authorization Server | Ứng dụng client và các thành phần liên quan |
|---|---|---|
| **Định danh và tài khoản** | Lưu/đồng bộ tài khoản, trạng thái và thuộc tính danh tính theo chính sách tổ chức. | Quyết định có tạo hồ sơ người dùng trong ứng dụng hay không, liên kết hồ sơ với danh tính IdP và xử lý người dùng bị chặn ở tầng nghiệp vụ. |
| **Kiểm tra thông tin đăng nhập** | Xác minh mật khẩu, passkey, liên kết danh tính, MFA, chính sách đăng nhập. | Chuyển người dùng qua kênh đăng nhập đúng IdP; không cần thu thập mật khẩu IdP. |
| **Đăng ký OAuth/OIDC client** | Lưu `client_id`, phương thức xác thực client, redirect URI được phép, scope/chính sách. | Cấu hình đúng `client_id`, bí mật nếu có, issuer, scope và URI callback; quản lý bí mật phía server. |
| **Yêu cầu đăng nhập** | Cung cấp authorization endpoint và áp dụng chính sách IdP. | Khởi tạo yêu cầu, chọn scope và redirect URI; liên kết yêu cầu với trình duyệt/phiên bằng `state`, `nonce` và PKCE khi áp dụng. |
| **Authorization Code** | Phát hành code ngắn hạn, ràng buộc với client/redirect URI và code challenge nếu dùng PKCE. | Tiếp nhận callback, kiểm tra `state` và trao đổi code qua token endpoint. |
| **ID Token** | Phát hành token mang thông tin xác thực OIDC và công bố khóa xác minh. | Kiểm tra token phù hợp với issuer/client/yêu cầu đăng nhập trước khi tin cậy danh tính. Spring Security hỗ trợ công việc này khi dùng OIDC login đúng cấu hình. |
| **Access Token** | Phát hành token để gọi tài nguyên theo scope/audience/chính sách. | Giữ token an toàn và gửi đúng API. **Resource Server** chịu trách nhiệm xác minh token và quyết định truy cập API. |
| **Refresh Token** | Có thể phát hành, luân chuyển, hết hạn hoặc thu hồi theo chính sách. | Lưu giữ an toàn và dùng để xin Access Token mới nếu được cấp và ứng dụng có cấu hình hỗ trợ. |
| **Thông tin hồ sơ/nhóm** | Cung cấp claim, UserInfo hoặc API danh mục người dùng tùy cấu hình. | Xác định claim nào đáng tin, ánh xạ chúng vào mô hình người dùng/quyền của ứng dụng. |
| **Quyền nghiệp vụ** | Có thể quản lý nhóm/role tập trung hoặc policy hỗ trợ. | Quyết định ai được duyệt đơn, xem dữ liệu phòng ban nào, sửa hồ sơ nào; kiểm tra tại nơi thực thi hành động. |
| **Phiên đăng nhập** | Quản lý phiên SSO tại IdP. | Quản lý phiên ứng dụng, cookie, thời hạn, CSRF, session fixation và đăng xuất cục bộ. |
| **Đăng xuất** | Cung cấp cơ chế kết thúc phiên IdP và/hoặc thu hồi token nếu sản phẩm hỗ trợ. | Hủy phiên ứng dụng, xóa trạng thái đăng nhập; phối hợp OIDC logout khi cần và khi IdP hỗ trợ. |
| **Nhật ký và kiểm toán** | Ghi nhận sự kiện xác thực, thay đổi tài khoản, MFA theo phạm vi IdP. | Ghi nhận hành động nghiệp vụ và quyết định phân quyền; bảo vệ dữ liệu, không ghi raw token/secret vào log. |

**Nguyên tắc thiết kế:** Chỉ chuyển trách nhiệm sang IdP đối với những gì IdP thực sự biết và kiểm soát. IdP có thể biết nhân viên thuộc nhóm `finance`, nhưng thường không thể biết đơn hàng số 123 thuộc bộ phận nào hoặc nhân viên có được phê duyệt đơn ấy ở thời điểm hiện tại hay không.

## 3. Một luồng OIDC đăng nhập diễn ra ở đâu?

Sơ đồ minh họa trường hợp ứng dụng Spring Boot hoạt động như **server-side OIDC Client** và có API ở phía sau:

```mermaid
sequenceDiagram
    autonumber
    participant B as Trình duyệt
    participant C as Spring Boot OIDC Client
    participant I as IdP / OpenID Provider
    participant A as Resource Server / API

    B->>C: Bắt đầu /oauth2/authorization/company
    C-->>B: Redirect tới authorization endpoint (state, nonce, scope, PKCE nếu dùng)
    B->>I: Yêu cầu xác thực /authorize
    I->>B: Đăng nhập / MFA / consent (theo chính sách)
    I-->>B: Redirect về callback với code và state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Kiểm tra state và yêu cầu đã lưu
    C->>I: Đổi authorization code tại token endpoint
    I-->>C: ID Token + Access Token (+ Refresh Token nếu được cấp)
    C->>C: Kiểm tra ID Token; tạo Authentication và phiên ứng dụng
    C-->>B: Cookie phiên; truy cập chức năng đã được phép
    C->>A: Gọi API với Bearer Access Token phù hợp
    A->>A: Xác minh Access Token và quyền truy cập tài nguyên
    A-->>C: Dữ liệu API được phép trả về
```

Các điểm chuyển giao trách nhiệm quan trọng:

1. **Khởi tạo yêu cầu:** Spring Security tạo authorization request và ghi lại trạng thái cần thiết để đối chiếu callback. Ứng dụng phải dùng issuer/endpoint, scope và redirect URI đã đăng ký, qua HTTPS trong môi trường thực tế.
2. **Người dùng xác thực tại IdP:** IdP lựa chọn cách kiểm tra danh tính, có thể yêu cầu MFA, hiển thị consent, từ chối tài khoản bị khóa hoặc tận dụng phiên SSO sẵn có. Ứng dụng không nhìn thấy mật khẩu IdP.
3. **IdP chuyển hướng trả code:** Code không phải ID Token hay Access Token. Với Authorization Code Flow, backend client đổi code tại token endpoint qua kênh phía server.
4. **Client kiểm tra kết quả:** `state` giúp phát hiện callback không khớp với yêu cầu đăng nhập trước đó. Với OIDC, client kiểm tra ID Token và `nonce` nếu nonce được gửi. Với PKCE, token endpoint xác nhận `code_verifier` khớp `code_challenge` của yêu cầu trước đó.
5. **Client tạo phiên riêng:** Spring Security tạo đối tượng `Authentication`, đặt vào `SecurityContext` và dùng cơ chế lưu phiên phù hợp. Người dùng đã đăng nhập tại IdP không đồng nghĩa mọi chức năng trong ứng dụng đều được cấp quyền.
6. **API kiểm tra quyền của chính API:** Khi client gọi API, Resource Server phải tự xác minh Access Token dành cho nó và áp dụng các quy tắc phân quyền của API.

`state`, `nonce` và **PKCE** bảo vệ các phần khác nhau của luồng: `state` liên kết callback với yêu cầu ban đầu; `nonce` ràng buộc ID Token với phiên yêu cầu OIDC nếu được dùng; PKCE giúp ngăn việc authorization code bị chặn rồi đổi token bởi bên không có `code_verifier`. Chúng không thay thế nhau. Với client công khai, Authorization Code + PKCE là mô hình thiết yếu; với backend confidential client, PKCE vẫn hữu ích khi được hỗ trợ và cấu hình.

## 4. Phân biệt ID Token, Access Token, Refresh Token và cookie phiên

Đây là nơi dễ xảy ra nhầm lẫn nhất khi phân chia trách nhiệm.

| Loại | Được phát hành/tạo bởi | Đối tượng sử dụng chính | Ý nghĩa và phạm vi tin cậy |
|---|---|---|---|
| **ID Token** | OpenID Provider | OIDC Client | Xác nhận sự kiện xác thực và danh tính người dùng cho **client nhận token**. Chứa các claim như `iss`, `sub`, `aud`, `exp`, `iat` và những claim khác khi áp dụng. |
| **Access Token** | Authorization Server | Resource Server / API; client chuyển tiếp khi gọi API | Cho phép truy cập API theo phạm vi và điều kiện được cấp. Có thể là JWT hoặc opaque token; API xác minh bằng cơ chế phù hợp. |
| **Refresh Token** | Authorization Server, nếu cho phép | Client đủ điều kiện được cấp | Xin Access Token mới mà không cần làm lại toàn bộ bước tương tác đăng nhập; chịu chính sách hết hạn, xoay vòng, thu hồi. |
| **Cookie phiên ứng dụng** | Ứng dụng Spring Boot hoặc hạ tầng phiên | Trình duyệt và backend ứng dụng | Giữ liên kết tới phiên đăng nhập cục bộ, ví dụ `JSESSIONID`; không phải token OIDC do IdP phát hành. |
| **Cookie phiên SSO** | IdP | Trình duyệt và IdP | Cho phép IdP nhận ra người dùng ở những lần chuyển hướng sau; không tự trao quyền truy cập dữ liệu của ứng dụng. |

### 4.1. Client phải tin ID Token theo những điều kiện nào?

Một ID Token không trở nên đáng tin chỉ vì nó có dạng JWT hoặc chứa tên/email hợp lệ. Trong OIDC login, client cần xác minh các ràng buộc thích hợp, bao gồm:

- **Chữ ký và khóa:** chữ ký hợp lệ theo khóa do issuer tin cậy công bố, chẳng hạn qua JWKS; chấp nhận thuật toán phù hợp chính sách.
- **Issuer (`iss`):** khớp OpenID Provider được cấu hình và tin cậy.
- **Audience (`aud`):** token được phát hành cho `client_id` của ứng dụng; xử lý `azp` khi trường hợp OIDC yêu cầu.
- **Thời gian:** `exp` còn hiệu lực, `iat` và các điều kiện thời gian khác hợp lệ theo quy tắc kiểm tra.
- **Ràng buộc phiên:** kiểm tra `nonce` khi yêu cầu OIDC đã gửi nonce; xem xét `auth_time` và mức xác thực nếu luồng có yêu cầu tương ứng.

Spring Security OIDC Client có cơ chế xử lý giao thức và kiểm tra ID Token cho luồng `oauth2Login` khi cấu hình đúng. Đội phát triển vẫn phải chọn đúng issuer tin cậy, quản lý cấu hình và không tự ý bỏ qua bước xác minh khi viết tích hợp tùy biến.

Để lưu khóa liên kết người dùng với dữ liệu nội bộ, thường dùng cặp **`(issuer, subject)`**, tức `iss` và `sub`. Không nên lấy email làm định danh bất biến: email có thể thay đổi, bị tái sử dụng hoặc chưa được xác minh. Claim `email_verified` cũng không tự động có nghĩa người dùng có mọi quyền trong ứng dụng.

### 4.2. Access Token không thay thế ID Token

Access Token có thể chứa `sub` và các claim khác, nhưng **không dùng nó làm bằng chứng đăng nhập OIDC thay cho ID Token**. Token có thể được cấp cho một API cụ thể, có audience khác với OIDC Client hoặc có định dạng opaque không thể đọc tại client.

Khi API nhận `Authorization: Bearer <access_token>`, chính API phải áp dụng các kiểm tra phù hợp:

- JWT: xác minh chữ ký, issuer, audience dành cho API, thời gian sống, scope và claim cần thiết.
- Opaque token: thường dùng introspection hoặc cơ chế do Authorization Server cung cấp để xác định token đang hoạt động và quyền gắn với token.
- Sau kiểm tra token: vẫn kiểm tra quyền nghiệp vụ như sở hữu đơn hàng, phạm vi tổ chức, trạng thái bản ghi và role áp dụng tại API.

**OIDC login thành công ở frontend không phải là bằng chứng cho phép một API khác bỏ qua bước kiểm tra bearer token.** Ngược lại, API xác minh một Access Token hợp lệ cũng không thay thế việc frontend quản lý phiên và CSRF nếu frontend sử dụng cookie.

### 4.3. Phiên ứng dụng khác phiên SSO

Giả sử người dùng đăng nhập vào cổng A, sau đó mở cổng B cùng dùng IdP:

- A và B có thể tận dụng phiên SSO chung tại IdP để không phải nhập lại mật khẩu.
- A vẫn có cookie phiên, timeout, dữ liệu người dùng nội bộ và phân quyền của A; B có tập riêng của B.
- Hết hạn phiên tại A không bắt buộc làm hết phiên SSO tại IdP. A có thể chuyển hướng đăng nhập lại và được IdP xác thực gần như ngay lập tức.
- Khóa tài khoản ở IdP, đổi mật khẩu hoặc đăng xuất SSO không bảo đảm tất cả phiên ứng dụng và JWT đã cấp mất hiệu lực ngay tức thì nếu các bên chưa có cơ chế đồng bộ hoặc thu hồi phù hợp.

Đối với ứng dụng web backend, ưu tiên giữ token ở phía server và dùng cookie phiên có cấu hình bảo mật phù hợp (HTTPS, `Secure`, `HttpOnly`, `SameSite` theo luồng thực tế). Client secret không được đưa vào JavaScript, URL, log hoặc bundle frontend. Nếu xây dựng SPA công khai hoặc ứng dụng di động, mô hình lưu trữ token và yêu cầu PKCE cần được thiết kế cho đúng loại client; không áp nguyên cấu hình confidential server-side client sang ứng dụng không thể bảo vệ secret.

## 5. Trong Spring Security, thư viện làm gì và lập trình viên phải làm gì?

Spring Security cung cấp cơ chế triển khai protocol; nó không biết trước quy tắc nghiệp vụ của từng hệ thống.

### 5.1. Hai cấu hình dễ bị nhầm

- **`oauth2Login()`:** đăng nhập người dùng vào ứng dụng qua OAuth 2.0/OIDC. Khi đăng ký có scope `openid` và IdP hỗ trợ OIDC, Spring Security xử lý OIDC login và tạo principal kiểu OIDC.
- **`oauth2Client()`:** hỗ trợ ứng dụng hoạt động như OAuth 2.0 Client khi cần lấy/quản lý token để gọi dịch vụ khác. Cơ chế authorized client và refresh phụ thuộc registration, grant type, cấu hình quản lý authorized client và thông tin token được IdP cấp.
- **`oauth2ResourceServer()`:** dùng cho endpoint API tiếp nhận bearer access token. Đây là trách nhiệm riêng của resource server, không mặc nhiên được bật chỉ vì có `oauth2Login()`.

Tùy kiến trúc, một ứng dụng có thể chỉ dùng `oauth2Login`, hoặc kết hợp các cấu hình ấy với những security filter chain và quy tắc truy cập phù hợp.

### 5.2. Ví dụ cấu hình một Spring Boot OIDC Client phía server

Giả sử IdP của công ty công bố metadata OIDC tại issuer `https://id.example.org/realms/company`. Các cấu hình dưới đây là minh họa; giá trị issuer, client registration và phạm vi truy cập phải khớp IdP thực tế.

Trong dự án Spring Boot dùng Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

Trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.org/realms/company
```

Ý nghĩa của các phần chính:

- `registration.company` là tên client registration trong Spring Security; liên kết tới đường dẫn khởi tạo đăng nhập mặc định `/oauth2/authorization/company`.
- `client-id` và `client-secret` là thông tin của ứng dụng **ở phía IdP**. Với confidential client, secret phải lấy từ biến môi trường/secret manager và chỉ tồn tại ở backend. Public client sử dụng cơ chế xác thực phù hợp loại client, không dựa vào một secret nhúng trong ứng dụng.
- `redirect-uri` là callback mặc định `/login/oauth2/code/company` sau khi Spring thay `{registrationId}`. URI thực tế phải được IdP cho phép.
- `scope` chứa `openid` để yêu cầu OIDC. `profile` và `email` là scope bổ sung, không bảo đảm mọi claim đều có trong ID Token.
- `issuer-uri` giúp Spring khám phá các endpoint và thông tin khóa theo metadata của issuer. Issuer phải được chọn và tin cậy qua cấu hình, không nhận tùy tiện từ tham số người dùng.

Ví dụ cấu hình HTTP security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình này, Spring Security có thể xử lý các bước chuẩn của OIDC login và chỉ cho người dùng đã xác thực truy cập các đường dẫn được bảo vệ. **Tuy nhiên, `hasRole("ADMIN")` không tự động hiểu nhóm của IdP.** Ứng dụng vẫn phải có quy tắc gán `ROLE_ADMIN` đáng tin cậy, nếu muốn người dùng thực sự vào `/admin/**`.

Đường dẫn đăng nhập mặc định để khởi tạo flow là `/oauth2/authorization/company`. Sau callback thành công, OIDC principal có thể được đọc trong controller:

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

`/me` minh họa cách ứng dụng nhận danh tính **đã được xử lý bởi tầng OIDC login**. Trong thực tế, ứng dụng thường lấy `(issuer, subject)` để tìm hồ sơ nội bộ rồi kiểm tra trạng thái và quyền nghiệp vụ trước khi trả dữ liệu.

### 5.3. Ánh xạ claim của IdP sang quyền ứng dụng

Giả sử IdP gửi claim `groups` trong ID Token và nhóm `portal-admins` được quản trị theo chính sách tổ chức. Ứng dụng có thể chọn ánh xạ nhóm ấy thành `ROLE_ADMIN`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Bean
GrantedAuthoritiesMapper userAuthoritiesMapper() {
    return authorities -> {
        Set<GrantedAuthority> mapped = new HashSet<>(authorities);

        for (GrantedAuthority authority : authorities) {
            if (authority instanceof OidcUserAuthority oidcAuthority) {
                List<String> groups =
                    oidcAuthority.getIdToken().getClaimAsStringList("groups");

                if (groups != null && groups.contains("portal-admins")) {
                    mapped.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                }
            }
        }

        return mapped;
    };
}
```

Đặt phương thức `@Bean` này trong một lớp `@Configuration`, chẳng hạn `SecurityConfig`. Mẫu minh họa dùng cú pháp Java 17+ và giả định claim `groups` được IdP cấu hình để xuất hiện trong **ID Token**. Nhiều IdP không gửi claim này mặc định, hoặc đặt nhóm tại UserInfo, Access Token hay API riêng. Khi đó phải tích hợp đúng nguồn và chính sách của IdP, thay vì giả định claim luôn tồn tại.

Ánh xạ nhóm bên ngoài vào role chỉ là **một cách** xác định quyền. Với ứng dụng nhạy cảm, ứng dụng có thể cần tra bảng role nội bộ, quyền theo tổ chức/dự án, chính sách duyệt nhiều cấp, hoặc kiểm tra quyền ở từng bản ghi. Không nên xem chỉ riêng `email` hoặc thuộc tính tự khai báo nào đó là đủ để có quyền quản trị.

Ví dụ, điều kiện `hasRole("ADMIN")` bảo vệ đường dẫn là bước đầu; thao tác «duyệt đơn hàng» còn cần kiểm tra đơn có thuộc chi nhánh được giao và người dùng có quyền duyệt ở thời điểm thao tác hay không.

### 5.4. Khi client gọi một API khác

Ứng dụng client có thể lấy Access Token thuộc OAuth 2.0 authorized client để gọi API được cho phép:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrderApiProxyController {

    private final RestClient restClient;

    public OrderApiProxyController(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    @GetMapping("/external-orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("https://api.example.org/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
```

Ví dụ này cho thấy **backend client sử dụng Access Token để gọi API**, không lấy ID Token thay thế. Trước khi áp dụng, IdP phải cấp token có audience, scope và quyền phù hợp với API đích; scope `openid profile email` của ví dụ đăng nhập bên trên không tự bảo đảm quyền gọi API đơn hàng. Trong hệ thống thật, nên tổ chức lớp HTTP client/authorized-client manager để xử lý token hết hạn, lỗi truy cập, retry có kiểm soát và không ghi token vào log.

Đồng thời, API `https://api.example.org/orders` phải có bảo mật resource server tương ứng. Client gửi bearer token không khiến API được phép tin ngay vào mọi nội dung request.

## 6. Những trách nhiệm không thể «ủy quyền hết» cho IdP

### 6.1. Phân quyền theo ngữ cảnh nghiệp vụ

IdP thường giỏi trả lời «đây là tài khoản nào?» và có thể trả lời «tài khoản này thuộc các nhóm nào?». Ứng dụng mới biết:

- Người dùng thuộc tenant, phòng ban hoặc dự án nào trong mô hình dữ liệu của ứng dụng.
- Người dùng có quyền xem/sửa **bản ghi cụ thể** không.
- Dữ liệu có ở trạng thái cho phép thao tác hay không.
- Một role quản trị của hệ thống A có tương ứng với role nào trong hệ thống B hay không.

Không nên dùng claim `sub`, `email` hoặc chỉ một nhóm tổng quát của IdP để bỏ qua kiểm tra ownership đối với tài nguyên cụ thể. API và tầng nghiệp vụ phải áp dụng quyền cho từng thao tác có rủi ro.

### 6.2. Quản lý vòng đời người dùng cục bộ

Khi đăng nhập lần đầu, ứng dụng có thể tự tạo hồ sơ từ `iss` và `sub` (just-in-time provisioning), hoặc yêu cầu quản trị viên phê duyệt trước. Đó là **quyết định của ứng dụng**. Ứng dụng cần quy định cách:

- Liên kết một danh tính IdP với tài khoản nghiệp vụ đang tồn tại mà không chiếm nhầm tài khoản.
- Xử lý user bị vô hiệu hóa ở ứng dụng dù IdP vẫn cho đăng nhập.
- Cập nhật thông tin hồ sơ thay đổi theo IdP mà không mất dữ liệu nghiệp vụ.
- Quản lý các trường hợp đổi IdP, nhiều issuer, nhiều tenant hoặc tài khoản được sáp nhập.

Nếu hỗ trợ đa tổ chức, không lấy `iss` do người dùng tự gửi rồi tin ngay để xác minh token. Mỗi issuer/tenant được chấp nhận phải nằm trong chính sách và registration đáng tin cậy của ứng dụng.

### 6.3. Bảo vệ ứng dụng sau khi đăng nhập

IdP hoàn thành MFA không tự làm an toàn một endpoint cho phép người dùng sửa địa chỉ email của người khác. Ứng dụng vẫn chịu trách nhiệm về:

- Kiểm soát truy cập ở URL, method và tầng nghiệp vụ; kiểm tra IDOR/ownership.
- CSRF khi dùng cookie phiên, chống session fixation, XSS và cấu hình cookie/HTTPS.
- Giới hạn dữ liệu nhạy cảm được đưa vào frontend, log, metrics và trace.
- Xử lý token, secret, session và dữ liệu người dùng trong bộ nhớ/lưu trữ.
- Chính sách thời hạn phiên hoặc yêu cầu xác thực lại cho thao tác nhạy cảm, nếu có.

`state` của OAuth/OIDC bảo vệ callback đăng nhập; nó **không thay thế** CSRF token cho các yêu cầu thay đổi dữ liệu nghiệp vụ. Tương tự, token có scope `orders.read` không có nghĩa người dùng được đọc mọi đơn hàng.

### 6.4. Đăng xuất và thu hồi

Đăng xuất có nhiều lớp:

1. **Local logout:** ứng dụng vô hiệu phiên, xóa `SecurityContext` và cookie phiên liên quan. Đây là phần client kiểm soát trực tiếp.
2. **RP-Initiated Logout:** ứng dụng có thể chuyển người dùng đến end-session endpoint của OpenID Provider, nếu IdP hỗ trợ và metadata/cấu hình phù hợp. Trong Spring Security có `OidcClientInitiatedLogoutSuccessHandler` cho trường hợp này.
3. **Thu hồi token hoặc phiên khác:** Authorization Server và những ứng dụng/resource server liên quan cần cơ chế tương ứng, ví dụ revocation, introspection, thời hạn token ngắn hoặc các giao thức logout được hỗ trợ.

**Local logout không đồng nghĩa IdP SSO logout.** Vì vậy, người dùng có thể bấm đăng xuất ở ứng dụng A, sau đó bấm đăng nhập và được IdP nhận diện lại mà không cần nhập mật khẩu. Đây không nhất thiết là lỗi của Spring Security.

Tương tự, logout ở IdP không tự động xóa cookie phiên tại tất cả ứng dụng nếu chúng không tích hợp cơ chế thông báo logout phù hợp. Với JWT access token tự chứa, việc thu hồi quyền ngay lập tức có thể cần thêm cơ chế ngoài kiểm tra chữ ký và `exp` thông thường.

## 7. Các tình huống minh họa để xác định đúng trách nhiệm

### Tình huống A: Đăng nhập thành công nhưng không mở được trang quản trị

Nhân viên đăng nhập qua IdP, nhận OIDC principal hợp lệ, nhưng khi vào `/admin` nhận HTTP `403 Forbidden`.

Đây có thể là **quyết định phân quyền đúng** của ứng dụng. Cần kiểm tra role nào được ứng dụng yêu cầu, nguồn quyền/claim nào đã được cấp, có quy tắc ánh xạ `ROLE_ADMIN` hay không, và nhân viên có thuộc phạm vi được phép không. Chỉ đăng nhập thành công không đủ để cấp quyền admin.

### Tình huống B: Trang web hiển thị tên người dùng nhưng gọi API trả HTTP 401

OIDC login đã thành công, nhưng token gửi API có thể hết hạn, sai issuer, không dành cho audience của API, hoặc endpoint đang thiếu bearer token. Nơi cần xem là cấu hình OAuth client khi xin token **và** cấu hình xác minh tại resource server.

Không giải quyết bằng cách gửi ID Token sang API «cho chắc». Phải cấp và sử dụng **Access Token phù hợp API**, rồi để resource server xác minh.

### Tình huống C: Hai hệ thống cùng SSO nhưng quyền khác nhau

Một nhân viên có thể là quản trị viên tại hệ thống nhân sự nhưng chỉ là người đọc tại hệ thống mua sắm. Cả hai đăng nhập qua cùng IdP và có thể nhận cùng danh tính, nhưng **mỗi hệ thống sở hữu phân quyền nghiệp vụ riêng**. Nhóm tập trung chỉ trở thành quyền khi hệ thống có quy tắc ánh xạ hợp lệ.

### Tình huống D: Người dùng đăng xuất nhưng đăng nhập lại ngay, không hỏi mật khẩu

Ứng dụng đã hủy phiên cục bộ, nhưng phiên SSO tại IdP vẫn còn. Muốn kết thúc cả SSO, cần tích hợp logout với IdP theo phương thức được hỗ trợ và xem xét tác động tới các ứng dụng khác cùng dùng SSO.

### Tình huống E: Người dùng bị khóa ở IdP nhưng đang mở ứng dụng

IdP thường chặn **lần xác thực tiếp theo**, trong khi ứng dụng có thể còn phiên đăng nhập cục bộ đang hoạt động. Nếu cần chặn truy cập gần thời gian thực, đội phát triển phải thiết kế chính sách hiệu lực phiên, đồng bộ trạng thái người dùng hoặc cơ chế thu hồi tương ứng; không giả định thao tác khóa ở IdP sẽ lập tức xóa mọi session và Access Token ở nơi khác.

## 8. Nhìn theo lỗi để chọn đúng nơi điều tra

| Triệu chứng | Nơi xem xét trước | Lý do |
|---|---|---|
| Đăng nhập thất bại do mật khẩu, MFA, tài khoản bị khóa. | IdP, chính sách xác thực và log đăng nhập. | IdP trực tiếp xử lý danh tính và phương thức xác thực. |
| IdP báo redirect URI không hợp lệ. | Cấu hình đăng ký client tại IdP và `redirect-uri` thực tế của Spring. | Hai phía phải khớp URI được phép; proxy/host/scheme có thể ảnh hưởng URL thực tế. |
| Callback bị từ chối vì `state` không khớp. | Phiên/trạng thái OAuth phía client, cookie, trình duyệt và reverse proxy. | Client phải liên kết callback với yêu cầu khởi tạo trước đó. |
| ID Token sai issuer hoặc audience. | Cấu hình issuer/registration phía client và cấu hình phát hành IdP. | Token phải được phát hành cho đúng client bởi issuer tin cậy. |
| Đăng nhập được nhưng chức năng trả `403`. | Quy tắc phân quyền, ánh xạ authority và quyền trên dữ liệu của ứng dụng. | Xác thực xong chưa có nghĩa được phép thực hiện chức năng. |
| API trả `401` dù giao diện web đã đăng nhập. | Access Token, API audience/scope, cấu hình resource server và đường gọi API. | API có cơ chế xác minh bearer token độc lập với phiên web. |
| Đăng xuất ở web nhưng SSO vẫn còn. | Phân biệt local logout và OIDC logout phía IdP. | Hai phiên được quản lý bởi hai hệ thống khác nhau. |

Các tên IdP, API và claim trong ví dụ đều là minh họa. Khi tích hợp thực tế, cần tra metadata của issuer, cấu hình client registration và hợp đồng claim/scope do nhà cung cấp định danh của hệ thống đó hỗ trợ.

Phạm vi đáng tin cậy cuối cùng được xác định tại **đúng điểm ra quyết định**: IdP xác thực và cấp token; OIDC Client kiểm tra kết quả đăng nhập, duy trì phiên và áp chính sách của ứng dụng; Resource Server xác minh token gọi API và kiểm tra quyền trên tài nguyên mà nó quản lý.
