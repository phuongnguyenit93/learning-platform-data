# Vai trò client, authorization server, resource server và end user trong OAuth 2.0 / OpenID Connect

## 1. Bài toán: ai làm gì khi người dùng đăng nhập và gọi API?

Một ứng dụng quản lý công việc muốn cho người dùng **đăng nhập qua hệ thống định danh tập trung** và sau đó **đọc báo cáo qua API**. Có bốn chủ thể với trách nhiệm khác nhau:

- **End user** (người dùng cuối): người đang thao tác, có thể quyết định hoặc được chính sách cho phép ứng dụng truy cập một tài nguyên thuộc quyền quản lý của họ.
- **Client**: ứng dụng muốn thay mặt người dùng truy cập tài nguyên, ví dụ trang web quản lý công việc hoặc ứng dụng di động.
- **Authorization server (AS)**: dịch vụ xác thực/chấp thuận quyền và cấp token cho client, ví dụ một hệ thống định danh hỗ trợ OAuth 2.0/OIDC.
- **Resource server (RS)**: dịch vụ giữ tài nguyên được bảo vệ, ví dụ API báo cáo, nhận và kiểm tra access token trước khi phục vụ yêu cầu.

**Phân biệt nền tảng:** OAuth 2.0 chủ yếu quy định cơ chế **ủy quyền truy cập tài nguyên**. OpenID Connect (OIDC) là lớp **xác thực danh tính người dùng** dựa trên OAuth 2.0; OIDC bổ sung ID token và quy tắc xác minh thông tin đăng nhập. Không suy luận rằng cứ thấy OAuth 2.0 là đã có đầy đủ giao thức đăng nhập.

Theo RFC 6749, OAuth 2.0 định nghĩa bốn **role** chính xác là `resource owner`, `client`, `authorization server` và `resource server`. Khi `resource owner` là một người, người đó được gọi là **end user**. Trong OIDC, các thuật ngữ quan trọng khác là `End-User`, `Relying Party` (RP, tức OIDC client) và `OpenID Provider` (OP, dịch vụ định danh hoạt động như authorization server hỗ trợ OIDC).

## 2. Bảng trách nhiệm và ranh giới tin cậy

| Chủ thể | Nắm giữ / xử lý | Việc phải làm | Việc không nên làm |
| --- | --- | --- | --- |
| **End user / resource owner** | Danh tính, quyền đối với dữ liệu, quyết định cho phép trong phạm vi chính sách | Tương tác với client; đăng nhập tại AS/OP khi được yêu cầu; xem quyền ứng dụng xin | Gửi mật khẩu cho client trong Authorization Code flow; tự tạo access token |
| **Client / RP** | `client_id`, phiên giao dịch, state, code verifier; có thể giữ secret nếu là confidential client | Khởi phát yêu cầu ủy quyền, nhận authorization code, đổi code lấy token, gọi RS; với OIDC kiểm tra ID token để tạo phiên đăng nhập | Tự ký token mạo danh AS; gửi ID token như bearer access token cho API; tin dữ liệu token chưa xác minh |
| **Authorization server / OP** | Thông tin client đã đăng ký, chính sách ủy quyền, endpoint ủy quyền và cấp token, khóa ký | Xác thực end user khi cần, đánh giá yêu cầu và chính sách, cấp access token và có thể refresh token; với OIDC phát ID token | Được mặc định coi là nơi lưu mọi tài nguyên của API; cấp token không giới hạn audience/scope |
| **Resource server** | API/tài nguyên được bảo vệ, chính sách truy cập, thông tin để xác minh token | Chỉ chấp nhận access token hợp lệ cho **chính API của mình**, thực hiện phân quyền theo scope/claim/quy tắc nghiệp vụ | Dùng ID token dành cho client làm bằng chứng được truy cập API; chấp nhận token chỉ vì decode được JWT |

**Ví dụ gán role:**
- Người dùng tên An: `end user` và thường là `resource owner` của bộ dữ liệu cá nhân.
- Web app `reports-web`: `client`; nếu dùng OIDC để đăng nhập, đây cũng là `Relying Party`.
- Dịch vụ `login.example.org`: `authorization server`; khi cung cấp OIDC, gọi là `OpenID Provider`.
- API `reports-api`: `resource server`.

Tên sản phẩm hoặc tên thư viện không tự xác định role. Một ứng dụng Spring Boot có thể vừa làm OAuth2 Client (gọi API khác) vừa làm Resource Server (bảo vệ API của chính nó). Một hệ thống có thể đặt AS và RS trong cùng hạ tầng, nhưng phải giữ riêng trách nhiệm cấp token và kiểm tra quyền tại tài nguyên.

## 3. Resource owner và end user: giống nhau ở đâu, khác nhau ở đâu?

**Resource owner** theo OAuth là chủ thể có quyền cho phép truy cập một tài nguyên; không nhất thiết phải là cá nhân. Khi tài nguyên thuộc người dùng và người ấy phê duyệt một quyền truy cập, `resource owner` chính là `end user`.

**End user** trong OIDC là người được OP xác thực, thường đăng nhập qua trình duyệt. Không đồng nhất ba khái niệm:
1. **Người đăng nhập**: một end user được OP chứng thực danh tính.
2. **Người có quyền cấp phép**: có thể là end user, tổ chức hoặc chính sách đã cấu hình trước.
3. **Chủ thể được token đại diện**: phụ thuộc grant và loại token; có thể là người dùng, client hoặc một tài khoản dịch vụ.

Ví dụ grant `client_credentials` thường là giao tiếp máy với máy: client xin access token dựa trên định danh/quyền của chính client hoặc sự ủy quyền đã được thiết lập trước. **Không có bước end user nhập mật khẩu hoặc bấm consent**, cũng không nhất thiết có ID token. Không nên ép mọi luồng OAuth 2.0 phải có một người dùng cuối.

Lưu ý thêm: màn hình “Đồng ý cho truy cập” (consent) không phải lúc nào cũng xuất hiện. Authorization server có thể dựa vào chính sách tổ chức, quyền đã được cấp trước hoặc trải nghiệm đã xác nhận trước đó. Việc không thấy hộp consent không có nghĩa không diễn ra kiểm tra authorization.

## 4. Client: ứng dụng xin token và sử dụng token

### 4.1. Client không đồng nghĩa với browser

`Client` là ứng dụng tham gia OAuth: backend web, SPA, mobile app, desktop app hoặc một service. **Browser/user-agent** thường chỉ là phương tiện đưa người dùng tới AS rồi quay về client trong Authorization Code flow.

Ví dụ người dùng mở trang web trên Chrome:
- **Chrome** là user-agent.
- **Backend web** quản lý phiên và thực hiện token exchange có thể là OAuth client.
- **Người dùng Chrome** là end user.
- Không phải mọi HTTP request phát từ browser đều biến browser thành một OAuth client độc lập.

### 4.2. Confidential client và public client

| Loại client | Nơi chạy và khả năng giữ bí mật | Hệ quả |
| --- | --- | --- |
| **Confidential** | Thành phần chạy trên server có thể giữ credential bảo mật | Có thể xác thực client tại token endpoint bằng secret hoặc cơ chế mạnh hơn; vẫn cần bảo vệ code flow |
| **Public** | SPA chạy trong browser, mobile/desktop app phân phối tới thiết bị người dùng | Không thể coi client secret nhúng trong mã là bí mật; cần Authorization Code + PKCE và các biện pháp ràng buộc luồng |

`client_id` là mã định danh đăng ký, **không phải bí mật**; `client_secret` chỉ có ý nghĩa là bí mật khi client có khả năng bảo vệ nó. Một frontend SPA không trở thành confidential client chỉ vì có chuỗi `client_secret` trong bundle JavaScript.

Client phải cấu hình đúng `redirect_uri` đã đăng ký, trạng thái request/response, scopes và token endpoint; chỉ gửi access token đến đúng RS cần thiết. Backend phục vụ browser thường dùng phiên riêng cho UI; việc API bên ngoài dùng access token không bắt buộc đồng nghĩa cookie phiên của web app không tồn tại.

## 5. Authorization server và OpenID Provider

Authorization server chịu trách nhiệm xử lý giao thức ủy quyền. Các chức năng phổ biến:

1. **Authorization endpoint**: nhận yêu cầu từ client qua user-agent, xác thực end user khi cần, thực thi policy/consent và trả authorization code qua redirect.
2. **Token endpoint**: xác minh authorization code, `redirect_uri`, PKCE `code_verifier` và cơ chế xác thực client (nếu áp dụng); sau đó cấp token.
3. **Token lifecycle**: xác định issuer, lifetime, audience, scope, grant, tùy tình huống refresh/revocation/introspection và chính sách bảo mật.
4. **Metadata/keys**: cung cấp thông tin discovery, JWKS nếu dùng token ký và endpoint theo chuẩn triển khai.
5. **OIDC bổ sung**: phát **ID token** chứa claims xác thực end user; có thể cung cấp `userinfo_endpoint` để RP đọc thông tin người dùng sau khi được cấp quyền phù hợp.

AS có thể ủy quyền việc kiểm tra mật khẩu/MFA cho một kho danh tính hoặc hệ thống bên ngoài; vì vậy **AS không nhất thiết là cơ sở dữ liệu user**. Với OIDC, OP phải hỗ trợ các quy tắc xác thực và phát ID token phù hợp, không chỉ là AS OAuth có endpoint cấp access token.

**Phân biệt authentication với authorization:** AS có thể xác nhận “An là ai” nhưng API báo cáo vẫn phải quyết định An có được đọc báo cáo số 42 hay không. Một `scope` như `reports.read` chỉ biểu diễn phạm vi quyền được cấp ở cấp token; quy tắc ownership/tenant cụ thể vẫn thuộc trách nhiệm authorization tại RS hoặc tầng nghiệp vụ.

## 6. Resource server: nơi thực sự bảo vệ dữ liệu

Resource server tiếp nhận yêu cầu như:

~~~http
GET /api/reports/42 HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...redacted
~~~

RS phải xác định token có hợp lệ để truy cập **API của nó** hay không. Với JWT access token, các bước kiểm tra thường bao gồm chữ ký/thuật toán được cho phép, issuer `iss`, thời hạn `exp` và `nbf`, **audience `aud`** phù hợp, cùng scope/claim/role và quyền truy cập từng tài nguyên. Với opaque token, RS thường dùng token introspection hoặc cơ chế xác minh được AS hỗ trợ. Loại token phụ thuộc AS và giao ước giữa AS–RS; **access token không bắt buộc là JWT**.

**Mốc quan trọng:** parse được payload Base64 của JWT không phải là xác thực token; kẻ tấn công cũng có thể tự tạo dữ liệu JWT chưa ký hợp lệ hoặc ký bằng khóa sai. Việc kiểm tra scope mà bỏ qua issuer/audience/signature là một lỗi bảo mật.

Nếu token hợp lệ nhưng thiếu quyền cần thiết, RS từ chối. Trong mô hình bearer token thông dụng: `401 Unauthorized` khi thiếu hoặc token không hợp lệ; `403 Forbidden` khi principal đã xác thực nhưng bị từ chối quyền. Tình huống thực tế có thể có quy tắc phản hồi khác nhau theo chuẩn/thiết lập, nên cần kiểm thử đúng dịch vụ.

### Resource server khác user-info service

OIDC `UserInfo Endpoint` trả thông tin định danh được phép xem cho RP khi có access token phù hợp. Nó cũng là endpoint tài nguyên được bảo vệ, nhưng **không phải API nghiệp vụ mà client được phép sử dụng tùy ý**. API báo cáo và UserInfo có thể nằm trên hai dịch vụ/khán giả token khác nhau. Không sử dụng ID token được cấp cho client để truy cập API báo cáo.

## 7. Luồng Authorization Code + PKCE: theo dõi từng vai trò

Đây là luồng điển hình cho ứng dụng có tương tác end user, với OIDC dùng `scope=openid`. Trình tự học tập:

~~~text
End user          Client / RP           Authorization Server / OP       Resource Server
   |                  |                            |                          |
   |-- Bấm "Đăng nhập" ->|                        |                          |
   |                  |-- Tạo state, PKCE, nonce -->| (chuẩn bị yêu cầu)       |
   |<-- Redirect tới authorization endpoint -------|                          |
   |------------------ Theo browser ---------------->|                          |
   |<----------------- Xác thực / consent ----------|                          |
   |------------------ Callback code + state ------>| Client nhận qua browser |
   |                  |-- Trao code + code_verifier --------------------------->|
   |                  |        (đường kết nối tới token endpoint của AS)       |
   |                  |<-- access_token + id_token (OIDC) -- AS                |
   |                  |-- Bearer access_token -------------------------------->|
   |                  |<--------------------- API response --------------------|
   |<-- Hiển thị dữ liệu --|                        |                          |
~~~

Để tránh hiểu nhầm do ký tự trong sơ đồ, các điểm kết nối thực tế là:
1. **End user → Client**: chọn thao tác cần đăng nhập/truy cập.
2. **Client → user-agent → AS**: gửi authorization request chứa `client_id`, `redirect_uri`, `response_type=code`, scope, `state`, `code_challenge`; với OIDC thường có `nonce` theo thiết kế xác thực.
3. **AS ↔ End user**: AS kiểm tra đăng nhập (có thể SSO/MFA) và chính sách/consent.
4. **AS → user-agent → Client**: chuyển hướng về `redirect_uri` với **authorization code** và `state` (hoặc thông báo lỗi).
5. **Client → AS token endpoint**: đổi code lấy token, gửi `code_verifier` và xác thực client nếu là confidential client.
6. **AS → Client**: trả access token; với OIDC Authorization Code flow có ID token; có thể có refresh token theo điều kiện cấp phát.
7. **Client → RS**: đính kèm **access token** trong header `Authorization: Bearer ...` để lấy dữ liệu.
8. **RS → Client → End user**: RS xác minh token, áp dụng authorization; client trình bày dữ liệu cho người dùng.

**Trách nhiệm bảo mật chia theo vai trò:** AS kiểm tra việc cấp token; Client bảo vệ authorization response, state, PKCE và token nhận được; RS phải tự thực hiện xác minh token và authorization cho API. Một lần AS xác thực thành công không cho phép RS bỏ qua kiểm tra quyền.

### 7.1. state, PKCE và nonce giải quyết các mục đích khác nhau

- **`state`**: dữ liệu ràng buộc request với callback, hỗ trợ chống CSRF và nhầm lẫn giao dịch. Client kiểm tra state trả về đúng giao dịch đã khởi phát.
- **PKCE**: client tạo `code_verifier` ngẫu nhiên, gửi `code_challenge` (ưu tiên phương thức `S256`) ở authorization request, gửi verifier thật ở token request. Nó làm code bị đánh cắp khó bị đổi lấy token. Public client phải dùng PKCE; khuyến nghị dùng cả cho confidential client theo RFC 9700.
- **`nonce` (OIDC)**: giá trị giao dịch trong authentication request, được phản ánh trong ID token để client phát hiện token phát lại/tráo đổi theo quy tắc OIDC. Nonce không thay thế kiểm tra chữ ký/issuer/audience của ID token.

Không mã hóa mật khẩu người dùng vào các trường này; không gửi `code_verifier` trong authorization request khi dùng S256. Các giá trị phải mới, đủ ngẫu nhiên và được gắn với đúng phiên giao dịch.

## 8. Authorization code, access token, ID token, refresh token

| Thành phần | Ai tạo / ai nhận | Dùng để làm gì | Không dùng làm gì |
| --- | --- | --- | --- |
| **Authorization code** | AS trả về client qua callback | Client đổi lấy token ở token endpoint, có ràng buộc thời gian/giao dịch | Gọi RS như Bearer token |
| **Access token** | AS cấp cho client; client gửi RS | Cho RS quyết định có tiếp nhận yêu cầu tài nguyên trong phạm vi ủy quyền không | Tự suy ra danh tính đăng nhập của RP như một ID token |
| **ID token** (OIDC) | OP cấp cho RP/client | Khẳng định sự kiện OP xác thực end user và các claims danh tính; RP phải xác minh | Làm Bearer token truy cập API nghiệp vụ |
| **Refresh token** (nếu cấp) | AS cấp cho client được phép; client gửi AS token endpoint | Yêu cầu cấp access token mới theo chính sách | Gửi trực tiếp RS hoặc đưa vào URL/public log |

**Audience khác nhau:**
- ID token có `aud` nhằm nhận diện **client_id của RP**.
- Access token được cấp để RS mục tiêu chấp nhận; audience/authorization details phải được thiết kế và kiểm tra theo chính sách AS–RS.

Cả ID token và access token có thể ở dạng JWT trong một triển khai, nhưng **cùng định dạng không có nghĩa cùng mục đích**. Phải kiểm tra đúng token type/use-case, issuer, chữ ký, thời hạn và audience. Không lưu token nhạy cảm trong logs, query string hay nơi dễ bị JavaScript không tin cậy đọc.

## 9. Cách các vai trò thể hiện trong Spring Security

Spring Security có các nhóm tính năng: **OAuth2 Client**, **OAuth2 Login** (trên nền Client), **OAuth2 Resource Server**. **Authorization Server** là trách nhiệm khác, có thể do một Identity Provider bên ngoài hoặc **Spring Authorization Server** đảm nhiệm. Việc thêm starter client/resource-server **không tự tạo authorization server**.

| Vai trò logic | Khả năng / cấu hình ứng dụng Java | Thường gặp |
| --- | --- | --- |
| Client/RP (web servlet) | `spring-boot-starter-oauth2-client`, `oauth2Login()`, `ClientRegistrationRepository` | Web app redirect sang OP, xử lý callback, tạo phiên đăng nhập |
| Client gọi API | `oauth2Client()`, `OAuth2AuthorizedClientManager` | Service/backend nhận và gắn Bearer access token khi gọi API |
| Resource Server (servlet) | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer(o -> o.jwt(...))` | REST API kiểm tra token, scope và authorization |
| Authorization Server/OP | IDP được quản lý hoặc Spring Authorization Server cấu hình riêng | Cung cấp authorize/token/JWKS/discovery, phát token |
| End user | Người thao tác, có thể trở thành `OidcUser` principal ở RP | Không phải service/bean riêng trong giao thức OAuth |

Với **reactive WebFlux**, các vai trò tương tự nhưng API Java thay bằng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveClientRegistrationRepository` và cấu hình OAuth2 tương ứng; không dùng code servlet của phần dưới nguyên xi cho reactive.

### 9.1. Ví dụ cấu hình Client/RP trong Spring Boot (minh họa có phụ thuộc OP)

Một web app Servlet sử dụng Java 17+, Spring Boot 3.3.x và dependency:

~~~groovy
// Trích dependencies của build.gradle, cần project Spring Boot 3.3.x đã cấu hình.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Security filter chain:

~~~java
// SecurityConfig.java trong ứng dụng Spring Boot Servlet; là lớp Java đầy đủ.
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Ví dụ `application.yml` (host và client registration chỉ mang tính mô phỏng; cần một OP thật/được cấp trong môi trường lab):

~~~yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      client:
        registration:
          reports-web:
            provider: training-op
            client-id: reports-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          training-op:
            issuer-uri: https://login.example.org/realms/training
~~~

Môi trường phải cung cấp biến `OIDC_CLIENT_SECRET`; không commit secret thật. OP phải có discovery hợp lệ, client được đăng ký với redirect URI trùng khớp; HTTPS bắt buộc ở môi trường thực. Link khởi tạo login thông dụng là `/oauth2/authorization/reports-web`, callback mặc định là `/login/oauth2/code/reports-web`. Với phạm vi `openid`, Spring Security dùng luồng OIDC và xác minh ID token theo cấu hình OP.

**Giới hạn ví dụ:** đoạn trên thể hiện client-side responsibility; không cung cấp OP tại domain minh họa và không thực thi đầy đủ flow nếu thiếu OP và client registration thật. PKCE cho confidential client và chính sách ràng buộc giao dịch cần cấu hình/kiểm tra theo phiên bản Spring Security, không kết luận rằng chỉ khai báo `oauth2Login()` tự động bảo đảm mọi khuyến nghị RFC 9700.

### 9.2. Ví dụ Resource Server nhận Bearer JWT

Trong một API Spring Boot riêng, phụ thuộc tối thiểu ở phía Spring Boot là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

File `src/main/java/demo/api/ApiApplication.java`:

~~~java
package demo.api;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/me")
                            .hasAuthority("SCOPE_reports.read")
                        .anyRequest().permitAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @GetMapping("/api/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject(), "status", "authorized");
    }
}
~~~

`application.yml` riêng cho API:

~~~yaml
server:
  port: 8081
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
~~~

Đoạn này dùng `scope`/`scp` trong access token để Spring Security thường chuyển sang authority tiền tố `SCOPE_`. Token có `reports.read` mới đáp ứng yêu cầu `SCOPE_reports.read`; nếu OP cấp cấu trúc claim khác thì phải cấu hình converter. **Triển khai production phải kiểm tra audience dành cho API và các yêu cầu bảo mật riêng**; việc chỉ có `issuer-uri` không đồng nghĩa mọi chính sách `aud` đã được kiểm tra theo mong đợi. Quy trình xác minh JWT cần issuer discovery/JWKS hợp lệ. Domain ví dụ không tồn tại để phục vụ flow thực tế.

Lệnh quan sát khi đã có một AS thực sự và access token hợp lệ cho API:

~~~bash
# Không có bearer credential: kỳ vọng 401 từ endpoint bảo vệ.
curl -i http://localhost:8081/api/me

# Có access token hợp lệ đúng issuer/audience/quyền:
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8081/api/me
~~~

Lệnh thứ hai chỉ trả dữ liệu khi token và policy đúng; `YOUR_ACCESS_TOKEN` chỉ là ký hiệu minh họa, không phải token sử dụng được. API không cần biết mật khẩu end user hay giữ client secret chỉ để xác minh một access token phù hợp.

## 10. Java 17 chạy độc lập: kiểm tra sơ đồ trách nhiệm

Bài tập sau chỉ in **sơ đồ vai trò** để nhớ ai chịu trách nhiệm bước nào. Nó không tạo token, không thực hiện cryptography và **không phải một OAuth server/client thật**. Tạo file `OAuthRolesDemo.java`:

~~~java
import java.util.List;

public class OAuthRolesDemo {
    record Role(String name, String responsibility) {}

    public static void main(String[] args) {
        List<Role> roles = List.of(
                new Role("End user", "yeu cau va dang nhap tai AS/OP"),
                new Role("Client", "xin code, doi token, goi API"),
                new Role("Authorization server", "xac thuc, uy quyen va cap token"),
                new Role("Resource server", "kiem tra access token va bao ve API")
        );

        roles.forEach(r ->
                System.out.println(r.name() + ": " + r.responsibility()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac OAuthRolesDemo.java
java OAuthRolesDemo
~~~

Kết quả chính xác:

~~~text
End user: yeu cau va dang nhap tai AS/OP
Client: xin code, doi token, goi API
Authorization server: xac thuc, uy quyen va cap token
Resource server: kiem tra access token va bao ve API
~~~

Điểm học tập là **tách trách nhiệm thành bốn thực thể logic**. Tại hệ thống thật, khi ghi mã cần dùng SDK/thư viện OAuth 2.0/OIDC đã kiểm chứng (như Spring Security), không tự phát minh cách ký, xác minh hay lưu token từ sơ đồ này.

## 11. Ba tình huống đối chiếu vai trò

### A. Web app đọc API với sự hiện diện của người dùng

An bấm “Xem báo cáo” trên `reports-web`. Web app redirect An tới OP, nhận code, đổi token, gửi access token tới `reports-api`. Nếu An đã đăng nhập SSO tại OP, bước nhập mật khẩu có thể được bỏ qua nhưng role của OP không thay đổi.

- An: end user/resource owner (nếu An có quyền định đoạt dữ liệu).
- `reports-web`: OAuth Client + OIDC RP.
- OP: authorization server xác thực/cấp token.
- `reports-api`: resource server bảo vệ báo cáo.

### B. Batch job gọi API hàng đêm không có end user

`nightly-export` tự chạy theo lịch và dùng `client_credentials` để xin token. Không có browser, redirect hay ID token đăng nhập end user.

- `nightly-export`: confidential client và có thể là principal được cấp quyền ở mức máy.
- AS: xác thực client và cấp access token theo scope/chính sách.
- RS: kiểm tra token/quyền của job rồi xử lý API.
- End user: không tham gia giao dịch này.

### C. Một Spring Boot app vừa là client vừa là resource server

Một gateway cung cấp `/api/admin` cho client bên ngoài, đồng thời gọi `billing-api` bằng token của chính nó. Cùng một process có thể có hai role:
- Đối với `/api/admin`, gateway là **resource server**.
- Khi gateway gọi `billing-api`, gateway là **client**.
- `billing-api` là **resource server** ở quan hệ thứ hai.
- AS/OP có thể là cùng một nhà cung cấp, nhưng client registration và audience/access policy có thể khác.

Vì vậy hãy **vẽ vai trò theo từng quan hệ HTTP/token**, không chỉ gắn một nhãn cố định cho cả hệ thống.

## 12. Sai lầm phổ biến và hậu quả

1. **“Client là người dùng.”** Sai: client là ứng dụng; end user là người sử dụng. Browser đóng vai user-agent, chưa chắc là OAuth client.
2. **“Authorization server là nơi giữ báo cáo nên tự cho phép đọc API.”** Sai: AS cấp token theo chính sách; RS quản lý API và phải kiểm tra token lẫn quyền truy cập tài nguyên cụ thể.
3. **“Đã đăng nhập OIDC thì access token và ID token dùng thay nhau.”** Sai: ID token hướng tới RP, access token hướng tới RS; audience và mục đích khác nhau.
4. **“Resource server có thể tin bất kỳ JWT parse được.”** Sai: cần xác minh chữ ký, issuer, thời hạn, audience và quyền; không chấp nhận token giả hoặc cấp cho API khác.
5. **“`scope=openid` nghĩa là quyền xem mọi dữ liệu profile.”** Sai: `openid` kích hoạt yêu cầu xác thực OIDC; scope/claim về dữ liệu và authorization tại RS là các lớp khác nhau.
6. **“Phải có consent popup ở mọi lượt.”** Sai: AS có thể áp dụng quyền đã cấp hoặc policy tổ chức; client không được tự bypass quy tắc của AS.
7. **“SPA giữ được secret vì JavaScript đã minify.”** Sai: mã phân phối tới trình duyệt không thể giữ client secret an toàn; dùng public-client pattern với PKCE.
8. **“Dùng password grant nhanh hơn.”** Theo RFC 9700, Resource Owner Password Credentials grant **không được sử dụng** trong thiết kế hiện đại; không thu mật khẩu người dùng qua client để tự đổi lấy token.
9. **“Implicit flow là lựa chọn mặc định cho frontend.”** RFC 9700 khuyến nghị tránh implicit grant vì rò rỉ/replay token; ưu tiên Authorization Code + PKCE cùng các kiểm soát phù hợp.
10. **“Spring Security Resource Server đã tạo sẵn endpoint `/authorize`, `/token`.”** Sai: đó là trách nhiệm AS; starter Resource Server chỉ hỗ trợ xác minh token và bảo vệ tài nguyên theo cấu hình.
11. **“Client có token valid thì luôn được xem mọi bản ghi cùng scope.”** Sai: RS cần kiểm tra tenant, ownership, role nghiệp vụ và chính sách từng object khi yêu cầu.
12. **“Refresh token gửi tới API để gia hạn request.”** Sai: refresh token là credential dành cho token endpoint của AS, không dành cho RS.

## 13. Bộ câu hỏi tự kiểm tra

**Câu 1.** Khi end user đăng nhập trên trang của OP, thành phần nào phải xác minh ID token trước khi dùng thông tin danh tính cho phiên ứng dụng?  
**Đáp án:** OIDC client/Relying Party. OP phát ID token, client kiểm tra theo quy tắc OIDC.

**Câu 2.** Khi API nhận `Authorization: Bearer ...`, ai phải bảo đảm token được cấp đúng cho API này và có scope đủ?  
**Đáp án:** Resource server, bằng quy trình xác minh token và authorization.

**Câu 3.** Một service dùng `client_credentials`, không có người dùng tương tác. Có thiếu một role bắt buộc không?  
**Đáp án:** Không; OAuth có các grant không yêu cầu tương tác end user tại thời điểm cấp token.

**Câu 4.** `reports-web` là web frontend còn `reports-api` là backend nội bộ. Có thể cấu hình cùng backend như client và resource server không?  
**Đáp án:** Có, vì role phụ thuộc loại giao dịch; cần thiết kế rõ các token/audience và security filter chain tương ứng.

**Câu 5.** OP cấp ID token có `aud=reports-web`. Có nên gửi ID token này tới `reports-api` như access token không?  
**Đáp án:** Không. ID token dành cho RP; RS cần access token được cấp cho tài nguyên phù hợp.

**Câu 6.** Một access token đã xác minh chữ ký và còn hạn nhưng `aud` chỉ API A; API B có được chấp nhận không?  
**Đáp án:** Không nếu token không nhắm tới B theo chính sách; chữ ký hợp lệ không tự mở rộng phạm vi audience.

### Checklist khi đọc kiến trúc OAuth/OIDC

- [ ] Xác định ai là end user/resource owner và có tham gia giao dịch không.
- [ ] Đặt tên rõ client và loại client (public/confidential).
- [ ] Xác định AS/OP; phân biệt login với token issuance.
- [ ] Xác định từng RS được bảo vệ và audience dự kiến.
- [ ] Nối đúng từng token với bên nhận: ID token → RP, access token → RS, refresh token → AS.
- [ ] Với user-interactive flow, dùng Authorization Code + PKCE, kiểm tra state, nonce/ID token nếu OIDC.
- [ ] Với máy với máy, cân nhắc client credentials và chính sách quyền riêng.
- [ ] Đánh giá permission trong API, tránh tin vào mỗi trạng thái “đã đăng nhập”.
- [ ] Không lưu log mã ủy quyền, secret, access/refresh token hoặc thông tin nhạy cảm.

## 14. Tài liệu chuẩn và tài liệu Spring

- [RFC 6749 — OAuth 2.0 Authorization Framework, `1.1 Roles](https://www.rfc-editor.org/rfc/rfc6749#section-1.1): định nghĩa chính thức bốn role OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): End-User, OP, RP, ID token và quy tắc kiểm tra.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): cơ chế PKCE.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị về Authorization Code, PKCE và các flow nên tránh.
- [Spring Security — OAuth2 Client, Login, Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/): khả năng ứng dụng Spring Security đảm nhiệm từng role.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): ví dụ xác minh Bearer JWT.

**Ghi nhớ:** **End user** thao tác/được xác thực; **client** xin quyền và dùng token; **authorization server** cấp token theo chính sách; **resource server** kiểm tra token và bảo vệ dữ liệu. OIDC bổ sung ID token để **client** hiểu ai vừa được xác thực, còn quyền truy cập API vẫn phải do **resource server** kiểm tra.