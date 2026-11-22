# Phân biệt OAuth 2.0 cấp quyền và OpenID Connect xác thực người dùng

**Chủ đề:** Spring Security – federation  
**Nhóm kiến thức:** Giao thức SSO

## 1. Cốt lõi: cấp quyền khác với xác thực

**OAuth 2.0 (authorization)** cho phép một ứng dụng (client) nhận quyền truy cập giới hạn tới tài nguyên hoặc API được bảo vệ, thông qua một Authorization Server. Câu hỏi mà OAuth 2.0 giải quyết là: **“Client có được phép gọi tài nguyên này, với phạm vi nào?”**

**OpenID Connect (OIDC, authentication)** là lớp xác thực danh tính chuẩn hóa **xây trên OAuth 2.0**. Câu hỏi OIDC giải quyết là: **“Người dùng nào vừa được nhà cung cấp danh tính xác thực cho ứng dụng này?”** OIDC bổ sung **ID Token**, các quy tắc kiểm tra danh tính, các claim chuẩn và (tùy nhu cầu) **UserInfo endpoint**.

Ví dụ:

- Một ứng dụng in ảnh xin quyền đọc ảnh trong tài khoản người dùng. Quyền gọi API ảnh là bài toán OAuth 2.0.
- Người dùng bấm “Đăng nhập bằng tài khoản công ty”; ứng dụng cần biết chắc người đăng nhập có định danh nào. Đây là bài toán OIDC.
- Một hệ thống vừa đăng nhập người dùng vừa gọi API thay mặt họ có thể dùng **cả OIDC và OAuth 2.0 trong cùng phiên**.

**Điểm dễ nhầm:** Authorization Server thường phải xác thực người dùng trước khi xin quyền. Điều đó **không biến giao thức OAuth 2.0 thuần túy thành giao thức đăng nhập**: OAuth 2.0 không định nghĩa một chứng cứ danh tính thống nhất dành cho client. Một số dịch vụ có API hồ sơ hoặc cách “login bằng OAuth” riêng, nhưng tính tương thích và kiểm tra danh tính không được bảo đảm bởi OAuth 2.0. OIDC chuẩn hóa phần còn thiếu đó.

## 2. Các vai trò và thuật ngữ

| Vai trò/khái niệm | Ý nghĩa |
| --- | --- |
| **Resource Owner** | Chủ thể có khả năng cấp quyền đối với tài nguyên, thường là người dùng. |
| **Client** | Ứng dụng muốn gọi API hoặc muốn đăng nhập người dùng. |
| **Authorization Server (AS)** | Hệ thống cấp authorization code, access token và thực hiện các bước liên quan đến cấp quyền. |
| **Resource Server (RS)** | API chứa tài nguyên, kiểm tra access token và quyết định cho phép truy cập. |
| **OpenID Provider (OP)** | Authorization Server có hỗ trợ OIDC và phát hành ID Token. |
| **Relying Party (RP)** | Client OIDC dựa vào kết quả xác thực của OP để tạo phiên đăng nhập riêng. |
| **Scope** | Phạm vi quyền client xin, ví dụ “orders.read”; việc cấp quyền còn tùy chính sách hệ thống. |
| **Claim** | Thuộc tính/khẳng định trong token hoặc phản hồi UserInfo, ví dụ “sub”, “email”, “iss”. |

Trong ứng dụng thực tế, một dịch vụ có thể đóng nhiều vai trò; ví dụ backend vừa là **OIDC client/RP** để đăng nhập web, vừa là **OAuth 2.0 resource server** để bảo vệ API.

## 3. So sánh trực tiếp

| Tiêu chí | OAuth 2.0 | OpenID Connect |
| --- | --- | --- |
| Mục đích chính | Ủy quyền truy cập API/tài nguyên | Xác thực người dùng cho client |
| Phần nào được chuẩn hóa? | Các grant, authorization endpoint, token endpoint và việc dùng access token | Bổ sung ID Token, claim danh tính, quy tắc xác minh, UserInfo, discovery |
| Dấu hiệu điển hình | Client xin quyền như “orders.read” | Authorization request chứa scope **openid** đến OP hỗ trợ OIDC |
| Token then chốt | **Access token** gửi đến resource server | **ID token** được RP xác minh cho sự kiện đăng nhập; có thể đồng thời có access token |
| Người nhận kiểm tra token | Resource server đối với access token | Relying Party/client đối với ID token |
| Định dạng token | Access token có thể là chuỗi opaque hoặc JWT; không mặc định là JWT | ID token là JWT |
| Câu hỏi sau thành công | “Token này cho phép truy cập những gì?” | “Ai đã được xác thực, bởi issuer nào, cho client nào?” |
| Có thể không có người dùng? | Có, ví dụ grant **client_credentials** cho máy gọi máy | Đăng nhập OIDC hướng đến người dùng cuối |

**OIDC không thay thế OAuth 2.0:** nó sử dụng cơ chế ủy quyền của OAuth 2.0, đồng thời bổ sung kết quả xác thực. Ngược lại, một access token OAuth 2.0 hợp lệ **không tự động là** ID token.

## 4. Luồng Authorization Code: cùng nền tảng, khác kết quả

### 4.1. OAuth 2.0 để cấp quyền gọi API

1. Client chuyển trình duyệt tới **authorization endpoint**, yêu cầu scope cần cho API (ví dụ “orders.read”).
2. Authorization Server xử lý đăng nhập nếu cần, chính sách và sự đồng ý của người dùng nếu áp dụng.
3. Trình duyệt được chuyển về **redirect URI** đã đăng ký cùng **authorization code**.
4. Client trao đổi code tại **token endpoint**; dùng **PKCE** để ràng buộc code với yêu cầu ban đầu.
5. Authorization Server cấp **access token**, có thể cấp refresh token tùy client và chính sách.
6. Client gọi API bằng header HTTP **Authorization: Bearer [access token]**.
7. Resource Server xác minh token, audience, thời hạn, scope/quyền rồi cho phép hoặc từ chối.

Kết quả của luồng này là khả năng truy cập tài nguyên. Client **không nên suy ra danh tính đã được xác thực theo chuẩn OIDC** chỉ từ việc nhận access token.

### 4.2. OIDC để đăng nhập người dùng

1. RP chuyển trình duyệt tới OP với authorization request, **scope chứa “openid”** (có thể thêm “profile”, “email”).
2. OP xác thực người dùng theo chính sách riêng (mật khẩu, passkey, MFA, phiên SSO hiện hữu...) và xử lý yêu cầu.
3. Với **Authorization Code Flow**, OP chuyển về RP cùng code; RP trao đổi code tại token endpoint.
4. OP trả về **ID token** và thông thường cả **access token**; refresh token tùy chính sách.
5. RP **xác minh ID token**: chữ ký, issuer, audience/client ID, hạn dùng và các điều kiện liên quan như nonce nếu đã gửi.
6. RP nhận danh tính ổn định từ cặp **(iss, sub)**, ánh xạ thành tài khoản ứng dụng, rồi tạo phiên đăng nhập riêng.
7. RP có thể gọi **UserInfo endpoint** bằng access token khi cần thêm hồ sơ; giá trị **sub** từ UserInfo phải khớp với ID token.

Luồng OIDC cũng có OAuth access token vì cần cơ chế token để lấy hồ sơ hoặc gọi API; **ID token mới là dữ liệu xác thực dành cho RP**. Một lần đăng nhập thành công **không có nghĩa** người dùng được phép làm mọi việc trong ứng dụng: phân quyền theo vai trò, policy và dữ liệu nghiệp vụ vẫn phải được đánh giá.

### 4.3. SSO liên quan như thế nào?

Khi nhiều ứng dụng cùng tin cậy một OP, người dùng có thể chuyển sang ứng dụng thứ hai và được xác thực lại thông qua **phiên đăng nhập tại OP** mà không cần nhập thông tin đăng nhập lần nữa. Mỗi ứng dụng vẫn tự duy trì phiên/cookie của mình và vẫn phải xác thực token đúng quy tắc. **Đăng nhập một lần không đồng nghĩa tự động đăng xuất đồng bộ**: logout ở RP, logout ở OP và single logout cần cơ chế, cấu hình riêng.

## 5. Ba loại token tuyệt đối không đánh đồng

### Access token – dùng để truy cập tài nguyên

- Được **resource server** tiêu thụ; thường được chuyển trong header Bearer.
- Có thể là **opaque token** (API cần introspection hoặc cơ chế xác thực tương ứng) hoặc **JWT** (API kiểm tra chữ ký và claim).
- Scope, audience, thời hạn, issuer và chính sách server quyết định khả năng truy cập. Có token **không bảo đảm** có mọi quyền.
- Resource server chỉ nên nhận token **được phát cho chính API đó**; với JWT, cần kiểm tra claim **aud** phù hợp.

### ID token – dùng để chứng minh sự kiện xác thực

- Là **JWT** do OP phát hành **cho client/RP**, không phải giấy phép gọi API.
- Claim quan trọng gồm: **iss** (issuer), **sub** (định danh subject), **aud** (phải bao gồm client_id của RP), **exp** (hết hạn), **iat** (thời điểm phát hành). **nonce** cần được kiểm tra nếu RP đã gửi nonce; có thể có **auth_time**, **acr**, **amr** tùy trường hợp.
- Chỉ **decode Base64URL để đọc JSON** là chưa đủ; phải xác minh chữ ký bằng khóa tin cậy, thuật toán được chấp thuận và các claim ràng buộc.
- **sub** phải được hiểu trong phạm vi **iss**. Email có thể đổi, tái sử dụng hoặc không được cung cấp; không dùng email làm khóa định danh duy nhất.
- Không chuyển ID token làm **Bearer** khi gọi API chỉ vì cả ID token và access token đều có thể trông như JWT.

### Refresh token – xin token mới

- Khi có, client sử dụng refresh token tại token endpoint để xin access token mới theo chính sách của Authorization Server.
- Refresh token **không phải ID token** và **không được gửi cho resource server**.
- Lưu trữ cẩn thận, giới hạn quyền truy cập và áp dụng rotation/sender constraint khi phù hợp; không ghi token vào log.

Ví dụ: nếu ID token có **aud = web-client**, còn API yêu cầu **aud = api://orders**, API phải từ chối ID token đó ngay cả khi chữ ký hợp lệ. **Chữ ký hợp lệ chỉ là một phần của điều kiện chấp nhận token.**

## 6. Spring Security: chọn đúng chức năng

Spring Security cung cấp các vai trò khác nhau:

| Tình huống | Chức năng Spring Security | Đầu vào/kết quả |
| --- | --- | --- |
| Web login với IdP hỗ trợ OIDC | **oauth2Login()** và client registration có scope **openid** | Xác minh ID token, tạo Authentication với **OidcUser** |
| OAuth 2.0 client cần gọi API | **oauth2Client()** / OAuth2AuthorizedClient | Quản lý authorization và access token để gọi API |
| API kiểm tra Bearer JWT | **oauth2ResourceServer().jwt()** | Xác minh JWT access token, tạo Authentication với principal **Jwt** |
| API kiểm tra opaque token | **oauth2ResourceServer().opaqueToken()** | Introspection qua Authorization Server |
| Muốn phát hành code/token/ID token | Dịch vụ authorization server/OP chuyên trách | Không phải trách nhiệm của **oauth2Login()** hay **resource server** |

**Lưu ý:** Khi client registration có scope **openid**, Spring Security chuyển sang xử lý OIDC (ví dụ **OidcUserService**). Không có scope này, login dựa trên OAuth 2.0 sử dụng cơ chế lấy hồ sơ nhà cung cấp (ví dụ **DefaultOAuth2UserService**) và **không có bảo đảm xác thực chuẩn OIDC**.

### 6.1. Ví dụ cấu hình Spring Boot 3.x, Spring Security 6.x, Java 17+

Ví dụ sau dành cho **một dự án Spring Boot có sẵn** (Servlet/MVC). Nó gồm một trang đăng nhập OIDC và một API bảo vệ bằng JWT access token. Bạn cần đăng ký client ở OP thật, cấu hình redirect URI và để OP phát hành token có audience/scope tương ứng; **mã không thể đăng nhập vào miền “example.org” minh họa**.

Các dependency cần có trong phần **dependencies** của pom.xml (dự án dùng Spring Boot parent/BOM phù hợp):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

**application.yml** – thay issuer bằng URL OP thực tế; cấp client ID/secret qua biến môi trường hoặc secret manager, không hard-code secret vào Git:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          training:
            issuer-uri: https://login.example.org/realms/training
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
          audiences:
            - api://training-api
~~~

- Spring dùng **issuer-uri** để khám phá metadata/khóa tin cậy của nhà cung cấp tương thích. OP phải cung cấp endpoint discovery hợp lệ.
- Đăng ký redirect URI của client trên OP, theo mặc định Spring là **{baseUrl}/login/oauth2/code/{registrationId}**; với registrationId “training”, ứng dụng thường dùng **/login/oauth2/code/training**.
- URL bắt đầu login do Spring cung cấp: **/oauth2/authorization/training**.
- Mục “audiences” yêu cầu JWT cho API chứa **api://training-api**. Hãy cấu hình OP phát token với audience đó; không mặc định rằng ID token hoặc mọi access token đều đáp ứng.
- Scope **openid/profile/email** phục vụ login; ví dụ API dưới đây yêu cầu scope **data.read** từ **access token riêng phù hợp**. Tên scope là quy ước của hệ thống, cần được OP cho phép.

**SecurityConfig.java** (package ví dụ **com.example.demo**):

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_data.read"))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**DemoController.java** (cùng package):

~~~java
package com.example.demo;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal OidcUser user) {
        return "OIDC subject: " + user.getSubject();
    }

    @GetMapping("/api/data")
    public String data(@AuthenticationPrincipal Jwt jwt) {
        return "API subject: " + jwt.getSubject();
    }
}
~~~

Trong một ứng dụng Spring Boot có lớp **@SpringBootApplication** tại package **com.example.demo** (hoặc package cha), chạy bằng **mvn spring-boot:run** sau khi cấu hình OP, client và biến môi trường. Đây là **mảnh cấu hình và controller hoàn chỉnh để đưa vào dự án Boot**, không phải dự án Maven độc lập vì còn cần pom.xml cha, lớp main và IdP đang hoạt động.

**Giải thích đúng hành vi:**

1. Trình duyệt truy cập **/me** chưa đăng nhập: web filter chain chuyển tới quy trình OIDC login. Sau xác thực thành công, controller nhận **OidcUser** và trả về subject đã xác minh (chuỗi phụ thuộc tài khoản, không có stdout cố định).
2. Request **GET /api/data** mang **Bearer access token JWT hợp lệ**, có audience **api://training-api** và scope **data.read**: API chain tạo **Jwt** principal và trả về chủ thể trong access token.
3. Token thiếu/hết hạn/sai issuer hoặc audience thường dẫn tới **401 Unauthorized**; token được chấp nhận nhưng thiếu **SCOPE_data.read** sẽ dẫn tới **403 Forbidden**.
4. ID token phát cho web client **không được dùng như access token** để gọi **/api/data**.
5. CSRF được vô hiệu **chỉ trên API dùng Bearer token phi trạng thái** trong ví dụ; web chain giữ bảo vệ CSRF mặc định cho các thao tác thay đổi trạng thái. Đừng vô hiệu CSRF toàn ứng dụng một cách máy móc.

Nếu ứng dụng chỉ làm web login, không cần API JWT chain. Nếu ứng dụng chỉ làm API, không cần **oauth2Login()**. Nếu access token là opaque, thay cấu hình JWT bằng introspection tương ứng.

### 6.2. Quyền truy cập trong ứng dụng khác với kết quả login

Sau khi có **OidcUser**, có thể ánh xạ **(issuer, subject)** vào bảng người dùng nội bộ, tải role hoặc permission từ hệ thống nghiệp vụ, rồi quyết định quyền xem/sửa dữ liệu. **Đăng nhập thành công không mặc nhiên đồng nghĩa được cấp quyền admin**. Ngay cả khi IdP trả claim nhóm/role, ứng dụng phải hiểu semantics của claim đó và áp dụng chính sách đáng tin cậy.

Trong resource server, Spring Security thường đổi mỗi scope trong JWT thành authority có tiền tố **SCOPE_**; ví dụ scope **data.read** thành **SCOPE_data.read**. Đây là cơ chế kiểm soát quyền cho API, không phải dấu hiệu cho biết trình duyệt đã thực hiện OIDC login.

## 7. Kiểm tra bảo mật bắt buộc trong triển khai thực tế

1. **Dùng Authorization Code Flow và PKCE**; public client bắt buộc dùng PKCE, confidential client nên dùng PKCE theo RFC 9700. Dùng phương thức **S256**. Tránh implicit flow và Resource Owner Password Credentials (ROPC) trong thiết kế mới.
2. **Ràng buộc request/response:** bảo vệ redirect URI, kiểm tra **state**/cơ chế chống CSRF thích hợp, dùng **nonce** khi áp dụng và kiểm tra nonce trong ID token nếu đã gửi. Không tự tạo callback bỏ qua cơ chế xác minh của thư viện.
3. **Xác minh ID token ở RP:** chữ ký/thuật toán, **iss**, **aud = client ID**, **exp**, các yêu cầu về nonce, azp và thời điểm xác thực tùy ngữ cảnh. Không tự tin tưởng một JWT chỉ vì đọc được payload.
4. **Xác minh access token tại API:** chữ ký/JWKS hoặc introspection, thời hạn, **issuer**, **audience dành cho API**, scope/permission và loại token đúng mục đích. Trong Spring Boot, cấu hình **issuer-uri** không có nghĩa tự động kiểm tra audience theo nghiệp vụ; cần thêm **audiences** hoặc validator thích hợp.
5. **Bảo vệ secret và token:** TLS, secret manager, thời hạn token ngắn hợp lý, lưu trữ an toàn và tuyệt đối không ghi access/ID/refresh token hoặc dữ liệu nhạy cảm vào log.
6. **Ổn định định danh:** dùng cặp **(iss, sub)** làm định danh liên kết; không giả định **email** luôn tồn tại, đã xác minh hoặc bất biến. Scope **email** chỉ là yêu cầu claim, không đảm bảo OP trả đầy đủ.
7. **Phân biệt phiên:** phiên SSO trên OP, phiên ứng dụng và vòng đời access/refresh token là các trạng thái khác nhau; cần thiết kế logout, session expiration, thu hồi quyền và reauthentication riêng.

## 8. Bài tập tình huống và đáp án

**Tình huống A:** Ứng dụng đọc lịch của người dùng bằng access token, nhưng không nhận ID token. Có thể tuyên bố “đã đăng nhập chuẩn OIDC” chưa?  
**Đáp án:** Chưa. Ứng dụng đã có quyền gọi API theo OAuth 2.0; thiếu bằng chứng danh tính OIDC được kiểm tra cho chính client.

**Tình huống B:** Sau OIDC login, client nhận ID token có **aud = portal-web**. Có dùng nó để gọi API **orders-api** không?  
**Đáp án:** Không. ID token dành cho RP. API cần access token được phát cho API, xác minh audience và quyền tương ứng.

**Tình huống C:** Service chạy mỗi đêm lấy báo cáo bằng **client_credentials**. “Ai đã đăng nhập”?  
**Đáp án:** Grant này xác thực/ủy quyền cho client máy gọi máy, không đại diện cho một lần người dùng cuối đăng nhập qua OIDC.

**Tình huống D:** Hai ứng dụng cùng OP; truy cập ứng dụng thứ hai không hỏi lại mật khẩu. Tại sao vẫn phải kiểm tra ID token?  
**Đáp án:** Có thể OP tái sử dụng phiên SSO, nhưng mỗi RP phải xác minh phản hồi dành riêng cho client của mình rồi mới tạo phiên cục bộ; SSO không loại bỏ kiểm tra chứng cứ danh tính.

**Tình huống E:** JWT access token có chữ ký đúng và còn hạn nhưng **aud** hướng tới API khác.  
**Đáp án:** API hiện tại phải từ chối token; chỉ kiểm tra chữ ký và exp là chưa đủ.

## 9. Checklist chọn giao thức

- **Chỉ cần hệ thống gọi API theo quyền đã cấp:** OAuth 2.0 (access token + resource server).
- **Cần đăng nhập liên kết người dùng/SSO:** OpenID Connect trên OAuth 2.0 (ID token + kiểm tra OIDC).
- **Cần cả login và gọi API:** OIDC cho xác thực tại RP, OAuth 2.0 access token cho từng resource server.
- **Cần phân quyền nội bộ:** áp dụng role/permission/policy của ứng dụng ngoài việc xác thực và kiểm tra scope của token.
- **Máy gọi máy không có người dùng cuối:** xem xét OAuth 2.0 client_credentials; không suy diễn có OIDC login.

**Ghi nhớ:** **OAuth 2.0 = ứng dụng được phép làm gì với tài nguyên. OIDC = người dùng nào đã được xác thực cho ứng dụng.** ID token hướng tới client/RP; access token hướng tới API/resource server.

## 10. Tài liệu chuẩn tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC Code Flow, claim và quy tắc xác minh.
- [RFC 6749 – OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): các vai trò, grant và token.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): PKCE, CSRF và các khuyến nghị an toàn hiện hành.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): OIDC login và client registration.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT access token, issuer, scope và audience.
- [Spring Boot – OAuth 2.0](https://docs.spring.io/spring-boot/reference/security/oauth2.html): cấu hình client và resource server.
