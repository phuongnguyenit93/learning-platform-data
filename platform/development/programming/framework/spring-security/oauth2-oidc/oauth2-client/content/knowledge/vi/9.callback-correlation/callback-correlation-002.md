# 9.2. HttpSessionOAuth2AuthorizationRequestRepository trong luồng Servlet

## 1. Bài toán: làm sao nối callback với lần bắt đầu đăng nhập?

Trong ứng dụng Spring Security OAuth 2.0/OIDC Client chạy trên **Servlet stack**, Authorization Code Flow có một đặc điểm quan trọng: yêu cầu đăng nhập bắt đầu tại ứng dụng, đi qua trình duyệt tới Authorization Server/OpenID Provider rồi quay về ứng dụng bằng một callback. Giữa hai thời điểm đó có thể có nhiều request khác, nhiều cửa sổ trình duyệt, hoặc nhiều người dùng đang đăng nhập đồng thời.

Ví dụ:

~~~text
GET /oauth2/authorization/company
    → Redirect tới https://idp.example.org/authorize?...&state=RANDOM_STATE

Người dùng đăng nhập tại IdP
    → Redirect về /login/oauth2/code/company?code=AUTH_CODE&state=RANDOM_STATE
~~~

Khi nhận callback, ứng dụng phải trả lời được những câu hỏi:

1. Callback này có thuộc **một authorization request hợp lệ đã khởi tạo trước đó** không?
2. Giá trị <code>state</code> trả về có trùng với yêu cầu đã lưu không?
3. Ứng dụng đã dùng **ClientRegistration** nào, redirect URI nào và scope nào khi bắt đầu flow?
4. Nếu dùng **PKCE**, <code>code_verifier</code> tương ứng với authorization code nằm ở đâu?
5. Làm thế nào lấy lại thông tin đó sau khi trình duyệt đã rời ứng dụng và quay lại?

**<code>HttpSessionOAuth2AuthorizationRequestRepository</code>** là thành phần mặc định của Spring Security OAuth2 Login Servlet giải quyết việc lưu và tra cứu **<code>OAuth2AuthorizationRequest</code> trong HTTP session**. Nó giúp Spring Security liên kết callback với yêu cầu đăng nhập đã khởi tạo và tiếp tục Authorization Code Flow.

Đây là lớp thuộc package:

~~~java
org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository
~~~

> **Phân biệt:** Repository này lưu *yêu cầu xin authorization code đang chờ hoàn tất*. Nó không phải kho lưu access token, refresh token, ID Token, ClientRegistration hoặc SecurityContext sau khi người dùng đăng nhập.

## 2. Các khái niệm tham gia vào correlation

| Khái niệm | Vai trò | Liên hệ với HTTP session |
|---|---|---|
| <code>OAuth2AuthorizationRequest</code> | Mô tả yêu cầu được gửi tới authorization endpoint: authorization URI, client ID, redirect URI, scope, state, additional parameters, attributes | Object được repository lưu tạm để callback tra cứu lại |
| <code>state</code> | Giá trị khó đoán, giúp liên kết authorization response với authorization request và hạn chế login CSRF | Là giá trị trong request đã lưu; callback phải mang state phù hợp |
| <code>HttpSession</code> | Vùng dữ liệu phía server gắn với phiên trình duyệt | Chứa authorization request giữa lượt redirect đi và về |
| Cookie phiên (<code>JSESSIONID</code> hoặc tên cấu hình khác) | Giúp browser gửi lại định danh HTTP session | Nếu callback không có cookie tương ứng, server có thể không tìm thấy authorization request |
| <code>code</code> | Authorization code do Authorization Server cấp | Dùng để trao đổi token sau khi xác nhận callback hợp lệ |
| <code>code_verifier</code> (PKCE) | Bí mật một lần của authorization request | Có thể nằm trong attributes của authorization request được Spring Security lưu |
| <code>ClientRegistration</code> | Cấu hình OAuth2/OIDC Client cho nhà cung cấp | Được tra bằng registration ID; không được lưu trữ bởi repository đang xét |

### 2.1. Repository lưu gì, không lưu gì?

<code>OAuth2AuthorizationRequest</code> có thể chứa các thông tin quan trọng:

- <code>authorizationUri</code>: URL authorization endpoint của nhà cung cấp.
- <code>authorizationGrantType</code>: thường là <code>AuthorizationGrantType.AUTHORIZATION_CODE</code>.
- <code>responseType</code>: thường là <code>code</code>.
- <code>clientId</code>, <code>redirectUri</code>, <code>scopes</code>.
- <code>state</code>: giá trị được dùng để correlate với callback.
- <code>additionalParameters</code>: có thể chứa các tham số như <code>nonce</code>, <code>code_challenge</code>, <code>code_challenge_method</code> tùy flow.
- <code>attributes</code>: dữ liệu nội bộ để client tiếp tục flow, ví dụ registration ID và PKCE verifier tùy cấu hình Spring Security.

Authorization request **khác** authorization response. Trong callback, Authorization Server trả về <code>code</code>, <code>state</code> hoặc thông tin lỗi. Repository giữ phía **request khởi tạo**, không phải kho lưu trữ authorization code hoặc access token đã cấp.

## 3. Luồng lưu, lấy lại và xóa authorization request

Spring Security OAuth2 Login Servlet có hai filter đáng chú ý:

- **<code>OAuth2AuthorizationRequestRedirectFilter</code>** xử lý đường dẫn bắt đầu đăng nhập (mặc định <code>/oauth2/authorization/{registrationId}</code>). Nó tạo <code>OAuth2AuthorizationRequest</code> qua resolver, lưu request bằng <code>AuthorizationRequestRepository</code>, rồi redirect browser tới Authorization Server.
- **<code>OAuth2LoginAuthenticationFilter</code>** xử lý callback (mặc định <code>/login/oauth2/code/{registrationId}</code>). Nó lấy authorization request đã lưu, kết hợp với authorization response nhận từ callback, rồi thực hiện quá trình xác thực và trao đổi token.

Các filter cần sử dụng **cùng một cơ chế repository/trạng thái** để request được lưu khi đi có thể được tìm thấy khi callback quay về.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security Servlet Client
    participant S as HttpSession
    participant OP as OpenID Provider
    U->>B: Chọn đăng nhập với company
    B->>C: GET /oauth2/authorization/company
    C->>C: Resolve ClientRegistration, tạo state và authorization request
    C->>S: saveAuthorizationRequest(request)
    C-->>B: HTTP 302 tới OP, mang state
    B->>OP: GET /authorize?...&state=...
    OP->>U: Xác thực và xin đồng ý nếu cần
    OP-->>B: HTTP 302 về callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>S: removeAuthorizationRequest(callback)
    S-->>C: OAuth2AuthorizationRequest đã lưu nếu state/session khớp
    C->>C: Tạo OAuth2AuthorizationExchange và kiểm tra correlation
    C->>OP: POST /token cùng authorization code và dữ liệu cần thiết
    OP-->>C: Token response
    C->>C: Xử lý OAuth2/OIDC authentication
    C-->>B: Đăng nhập thành công / failure handling
~~~

Trong trình tự thông thường:

**Bước 1 — Khởi tạo authorization request.** Người dùng truy cập URL như <code>/oauth2/authorization/company</code>. Spring Security tìm <code>ClientRegistration</code>, tạo state ngẫu nhiên, dựng authorization request và bổ sung các tham số phù hợp như PKCE nếu đã cấu hình.

**Bước 2 — Lưu vào HTTP session.** Trước khi chuyển hướng, <code>OAuth2AuthorizationRequestRedirectFilter</code> gọi repository để lưu authorization request. Browser nhận response redirect cùng cookie phiên nếu phiên được tạo tại thời điểm đó.

**Bước 3 — Redirect tới provider.** Provider nhận authorization request có <code>state</code> nhưng không nhận nội dung HTTP session phía ứng dụng. Với PKCE S256, provider nhận <code>code_challenge</code>, không được nhận <code>code_verifier</code> trong authorization URL.

**Bước 4 — Callback quay về.** Browser chuyển hướng tới <code>/login/oauth2/code/company</code> kèm <code>code</code> và <code>state</code>. Browser cũng phải gửi lại cookie phiên phù hợp để ứng dụng đọc đúng session.

**Bước 5 — Tra cứu và consume request.** <code>OAuth2LoginAuthenticationFilter</code> gọi repository để lấy và xóa authorization request tương ứng. Nếu session hoặc state không khớp, việc xây dựng authorization exchange không thể tiếp tục hợp lệ.

**Bước 6 — Trao đổi token và hoàn thành authentication.** Client dùng authorization code cùng thông tin request gốc để gọi token endpoint. Với OIDC, Client xác minh ID Token theo issuer, audience, signature và các quy tắc tương ứng trước khi coi người dùng đã xác thực.

> Việc **xóa authorization request sau khi dùng** rất quan trọng: trạng thái chờ callback chỉ có vòng đời của một lần đăng nhập và không nên được tái sử dụng.

## 4. Hợp đồng AuthorizationRequestRepository

<code>HttpSessionOAuth2AuthorizationRequestRepository</code> triển khai:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Các phương thức cốt lõi:

~~~java
OAuth2AuthorizationRequest loadAuthorizationRequest(HttpServletRequest request);

void saveAuthorizationRequest(
    OAuth2AuthorizationRequest authorizationRequest,
    HttpServletRequest request,
    HttpServletResponse response);

OAuth2AuthorizationRequest removeAuthorizationRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

Đây là chữ ký API rút gọn để học; trong Spring Security 6 các Servlet type thuộc namespace <code>jakarta.servlet.http</code>.

| Phương thức | Thời điểm thường dùng | Tác dụng |
|---|---|---|
| <code>saveAuthorizationRequest(...)</code> | Trước khi redirect tới Authorization Server | Ghi authorization request vào kho lưu giữ |
| <code>loadAuthorizationRequest(...)</code> | Khi cần đọc request đang chờ callback | Trả về request tương ứng nếu trạng thái hợp lệ, nếu không trả <code>null</code> |
| <code>removeAuthorizationRequest(...)</code> | Khi xử lý callback và dùng request gốc | Trả về request phù hợp, đồng thời loại bỏ trạng thái đã dùng |

### 4.1. Cách implementation mặc định kiểm tra state

Ở implementation session mặc định, repository dựa vào <code>state</code> trong callback để đối chiếu với <code>state</code> của authorization request đang lưu trong session. Nếu request không có state, không có session/request tương ứng, hoặc state khác, thao tác load không trả về authorization request hợp lệ.

Mô tả logic khái niệm:

~~~text
loadAuthorizationRequest(callback):
    callbackState = callback.query["state"]
    savedRequest = session.authorizationRequest
    if callbackState rỗng hoặc savedRequest không tồn tại:
        return null
    if callbackState != savedRequest.state:
        return null
    return savedRequest

removeAuthorizationRequest(callback):
    request = loadAuthorizationRequest(callback)
    nếu request hợp lệ:
        xóa request đã lưu khỏi session
    return request
~~~

Đây là **pseudocode**, không phải mã nguồn nội bộ Spring Security. Điểm cần hiểu là repository không tin một callback chỉ vì nó có <code>code</code> hợp lệ theo hình thức; nó phải tìm lại được request mà Client đã thực sự phát đi và kiểm tra state.

### 4.2. Mặc định thường lưu một authorization request tại một thời điểm

<code>HttpSessionOAuth2AuthorizationRequestRepository</code> mặc định lưu **một authorization request hiện hành trên một thuộc tính session** thay vì giữ bản đồ nhiều request độc lập theo state.

Ví dụ người dùng mở hai tab cùng dùng một HTTP session:

~~~text
Tab A: bắt đầu login A → lưu request A (state=A)
Tab B: bắt đầu login B → ghi đè bằng request B (state=B)
Tab A: callback về với state=A → session đang giữ state=B
Kết quả: repository không tìm được request phù hợp cho A
~~~

Flow của tab B có thể còn hợp lệ nếu request B chưa bị thay thế và session vẫn tồn tại. Khi ứng dụng thường xuyên có đăng nhập song song, nhiều tab hoặc nhiều provider chạy cùng lúc, cần cân nhắc repository tùy biến hỗ trợ nhiều authorization request theo state, có giới hạn số lượng và thời gian tồn tại rõ ràng.

Không tự kết luận rằng lỗi state luôn do tấn công; tình huống tab B ghi đè request A là một nguyên nhân vận hành thực tế.

## 5. Cấu hình mặc định trong Spring Boot OAuth2 Login

Với Spring Boot 3 và Spring Security 6, khai báo OAuth2 Client starter và một ClientRegistration là đủ để bắt đầu dùng OAuth2 Login Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Ví dụ <code>application.yml</code> cho OIDC provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: company-web
            client-secret: replace-with-secret-from-secure-storage
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Những URI và credential này là placeholder. Khi triển khai thực tế, lấy client secret từ secret manager/biến môi trường và đăng ký chính xác redirect URI trên OP. <code>issuer-uri</code> là issuer gốc, không phải URL Discovery Document.

Một bean bảo mật tối thiểu:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Khi gọi <code>.oauth2Login(Customizer.withDefaults())</code>, Spring Security cấu hình các thành phần của OAuth2 Login, trong đó authorization request repository mặc định cho Servlet là **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>**. Với trường hợp thông thường, không cần tự tạo repository bằng Java.

Ứng dụng khởi động flow từ:

~~~text
GET /oauth2/authorization/company
~~~

IdP redirect về callback:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

Filter xử lý callback cần nhìn thấy **cùng HTTP session** mà authorization request được lưu trước đó.

## 6. Khai báo repository tường minh bằng Java

Khi muốn tự cấu hình thành phần phục vụ correlation, có thể chủ động cung cấp một instance repository cho authorization endpoint của OAuth2 Login:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

@Configuration
public class ExplicitAuthorizationRequestRepositoryConfig {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
            authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)));

        return http.build();
    }
}
~~~

Đây là **cấu hình thay thế** cho bean <code>SecurityFilterChain</code> trong mục 5, không khai báo cả hai bean đồng thời nếu không có thiết kế nhiều chain rõ ràng. Lời gọi <code>authorizationRequestRepository(repository)</code> trên DSL OAuth2 Login là cách thông dụng để Spring Security dùng repository được chỉ định trong luồng.

Phần cấu hình vẫn dựa vào HTTP session, không thay đổi cơ chế correlation mặc định. Giá trị của cấu hình tường minh là khả năng thay thế repository bằng implementation khác hoặc kiểm soát dependency trong thiết kế ứng dụng.

**Lưu ý:** Đăng ký một bean <code>AuthorizationRequestRepository</code> trong Spring context **không có nghĩa mọi filter sẽ tự động dùng nó** ở mọi phiên bản hoặc mọi cấu hình. Nên cấu hình nó qua DSL của OAuth2 Login hoặc các điểm mở rộng được framework hỗ trợ, thay vì giả định chỉ cần tạo bean là đủ.

### 6.1. Khi nào nên tự cấu hình?

- Ứng dụng muốn thay đổi nơi lưu authorization request (ví dụ repository theo state hỗ trợ nhiều tab hoặc lưu trong backend phù hợp).
- Cần kiểm soát hành vi khi có nhiều provider/tenant hoặc thêm metadata nội bộ trong flow.
- Muốn truyền cùng một repository tới các thành phần liên quan khi tự cấu hình authorization request resolver hoặc OAuth2 Login filter.
- Cần kiểm thử các trường hợp state/session mất, callback sai hoặc login đồng thời.

Nếu không có yêu cầu riêng, giữ cấu hình mặc định giúp giảm lượng mã phải duy trì.

## 7. Quan sát API save, load và remove bằng Spring Mock Servlet

Ví dụ dưới đây minh họa hành vi repository **không cần gọi Authorization Server**. Nó cho thấy request chỉ được lấy lại khi callback mang đúng state và cùng session.

Trong dự án dùng Spring Boot, <code>spring-boot-starter-test</code> thường cung cấp <code>spring-test</code> với các mock servlet object.

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

class AuthorizationRequestRepositoryExampleTest {

    @Test
    void callbackMustUseSameSessionAndState() {
        var repository = new HttpSessionOAuth2AuthorizationRequestRepository();

        var authorizationRequest = OAuth2AuthorizationRequest.authorizationCode()
            .authorizationUri("https://idp.example.org/oauth2/authorize")
            .clientId("company-web")
            .redirectUri("https://app.example.org/login/oauth2/code/company")
            .state("random-state-for-this-example")
            .build();

        var start = new MockHttpServletRequest(
            "GET", "/oauth2/authorization/company");
        var startResponse = new MockHttpServletResponse();

        // Ghi request trước khi browser rời ứng dụng.
        repository.saveAuthorizationRequest(
            authorizationRequest, start, startResponse);

        var session = (MockHttpSession) start.getSession(false);
        assertNotNull(session);

        // Callback đúng session, đúng state.
        var callback = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        callback.setSession(session);
        callback.setParameter("state", "random-state-for-this-example");

        var loaded = repository.loadAuthorizationRequest(callback);
        assertNotNull(loaded);
        assertEquals(authorizationRequest.getState(), loaded.getState());

        var removed = repository.removeAuthorizationRequest(
            callback, new MockHttpServletResponse());
        assertNotNull(removed);
        assertNull(repository.loadAuthorizationRequest(callback));
    }
}
~~~

Đây là ví dụ ở mức **repository API**, không phải kiểm thử OAuth2 Login end-to-end: nó không xác minh authorization code tại token endpoint, ID Token hoặc SecurityContext. Giá trị state là chuỗi cố định chỉ nhằm minh họa; trong hệ thống thật, Spring Security tạo giá trị khó đoán cho mỗi flow.

### 7.1. Callback sai state

Nếu dùng lại session nhưng thay state:

~~~java
callback.setParameter("state", "unrelated-state");
OAuth2AuthorizationRequest result =
        repository.loadAuthorizationRequest(callback);
assertNull(result);
~~~

Callback này không được coi là authorization response cho request đã lưu. Trong flow thực tế, Spring Security có thể xử lý như thất bại đăng nhập vì không tìm thấy authorization request phù hợp.

### 7.2. Callback ở session khác

Nếu tạo request callback mới **không gắn** <code>MockHttpSession</code> trước đó:

~~~java
var differentBrowser = new MockHttpServletRequest(
    "GET", "/login/oauth2/code/company");
differentBrowser.setParameter(
    "state", "random-state-for-this-example");

assertNull(repository.loadAuthorizationRequest(differentBrowser));
~~~

Dù state giống, repository vẫn không tìm được request vì không có HTTP session chứa authorization request tương ứng. Đây là đặc điểm quan trọng giúp ràng buộc callback vào phiên đã khởi tạo đăng nhập.

## 8. State, session và PKCE phối hợp như thế nào?

Ba yếu tố giải quyết những phần khác nhau của Authorization Code Flow:

| Yếu tố | Xuất hiện ở đâu? | Bảo vệ điều gì? |
|---|---|---|
| <code>state</code> | Authorization request và callback | Correlate authorization response với request ban đầu; giảm nguy cơ login CSRF |
| HTTP session | Ở browser qua cookie định danh, dữ liệu thực ở server | Giúp Client tìm lại authorization request và thông tin cần thiết khi callback |
| PKCE <code>code_verifier</code> | Client giữ khi bắt đầu, gửi đến token endpoint khi đổi code | Ràng buộc authorization code với bên đã khởi tạo authorization request |

Với PKCE S256:

~~~text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
~~~

Trong lúc gửi authorization request, Client có thể gửi <code>code_challenge</code> và <code>code_challenge_method=S256</code> tới OP, đồng thời giữ <code>code_verifier</code> trong thuộc tính nội bộ của authorization request đã lưu. Khi callback về và state/session phù hợp, Spring Security lấy verifier đó để đưa vào token request.

Nếu một custom repository chỉ lưu <code>state</code> và <code>redirectUri</code> mà làm mất attributes của <code>OAuth2AuthorizationRequest</code>, PKCE có thể thất bại dù callback có state đúng. Vì vậy, khi thay thế repository, cần giữ được **toàn bộ thông tin mà token exchange cần**, không chỉ hai tham số xuất hiện trên URL.

### 8.1. OIDC nonce có giống state không?

Không. Trong OIDC, <code>nonce</code> (nếu được sử dụng) giúp liên kết **ID Token** với yêu cầu xác thực; nó được gửi trong authorization request và được kiểm tra theo yêu cầu OIDC. <code>state</code> giúp liên kết **authorization response/callback** với authorization request.

Spring Security có thể lưu dữ liệu cần thiết để kiểm tra nonce trong authorization request/attributes, tùy flow và phiên bản. Không tự thay <code>state</code> bằng nonce hoặc bỏ kiểm tra issuer, audience, chữ ký ID Token vì đã có session.

## 9. Vì sao callback mất session?

HTTP session thường được định danh bằng cookie từ browser, chẳng hạn <code>JSESSIONID</code> (tên cụ thể phụ thuộc Servlet container, Spring Session và cấu hình ứng dụng). Khi browser rời ứng dụng sang IdP rồi quay lại, cookie phải được gửi lại theo các quy tắc của browser và server.

Một số nguyên nhân phổ biến:

**Cookie không được gửi ở callback.** Cookie bị chặn bởi cấu hình <code>SameSite</code>, <code>Secure</code>, <code>Domain</code> hoặc <code>Path</code> không phù hợp. Với Authorization Code Flow callback dạng **top-level GET**, <code>SameSite=Lax</code> thường cho phép gửi cookie trên cross-site navigation; nếu provider dùng <code>response_mode=form_post</code> (POST cross-site), cách xử lý cookie có thể khác và cần cấu hình cẩn thận.

**Session đã hết hạn hoặc bị vô hiệu hóa.** Người dùng để lâu ở trang IdP, ứng dụng timeout session, logout ở tab khác hoặc một thành phần gọi <code>invalidate()</code> làm mất dữ liệu chờ callback.

**Nhiều instance không chia sẻ session.** Start request đến instance A, callback đến instance B và B không có session tương ứng. Load balancer không có sticky session hoặc hệ thống chưa có session store dùng chung có thể gây lỗi ngắt quãng.

**Host/port/scheme thay đổi.** Start URL dùng <code>localhost</code>, callback dùng IP nội bộ hoặc tên miền khác; cookie thuộc host ban đầu sẽ không được browser gửi đúng lúc. Reverse proxy cấu hình sai external host/scheme cũng làm redirect URI hoặc cookie bị lỗi.

**Nhiều tab ghi đè authorization request.** Tab thứ hai tạo request mới trong cùng session; tab đầu callback với state cũ và không tìm được request phù hợp.

**Repository tùy biến làm mất dữ liệu.** Việc serialize/deserialize không đầy đủ <code>OAuth2AuthorizationRequest</code>, lưu sai key hoặc dùng repository khác giữa start và callback có thể khiến dữ liệu không được tìm lại.

### 9.1. Cookie và chính sách trình duyệt

Các thuộc tính cookie cần hiểu:

| Thuộc tính | Vai trò | Ảnh hưởng đến callback |
|---|---|---|
| <code>Secure</code> | Cookie chỉ được gửi trên kết nối an toàn phù hợp | Ứng dụng production dùng HTTPS; cần cấu hình proxy và cookie chính xác |
| <code>HttpOnly</code> | Hạn chế JavaScript đọc cookie | Bảo vệ cookie phiên khỏi truy cập qua script; không quyết định riêng việc có gửi callback hay không |
| <code>SameSite</code> | Kiểm soát việc gửi cookie trong ngữ cảnh cross-site | Ảnh hưởng chuyển hướng GET hoặc POST từ IdP |
| <code>Domain</code> | Phạm vi host của cookie | Callback về host khác có thể không được gửi cookie |
| <code>Path</code> | Phạm vi URL path của cookie | Callback nằm ngoài path cookie có thể thiếu session |
| <code>Max-Age</code>/<code>Expires</code> | Thời hạn cookie | Cookie hết hạn trước callback dẫn đến không tìm thấy session |

<code>SameSite=None</code> chỉ nên được lựa chọn khi có nhu cầu cross-site rõ ràng và phải đi với <code>Secure</code> theo yêu cầu trình duyệt hiện đại. Không tắt bảo vệ cookie trên toàn ứng dụng để khắc phục một lỗi callback khi chưa xác định được nguyên nhân.

### 9.2. Ứng dụng nhiều instance với Spring Session

Trong kiến trúc nhiều instance, có thể dùng Spring Session với kho lưu trữ dùng chung (ví dụ Redis) để các node truy cập cùng HTTP session theo cookie browser. Khi đó authorization request lưu trong session có thể được truy cập bất kể callback tới node nào, miễn là các node dùng cấu hình session tương thích.

Không nhầm <code>HttpSessionOAuth2AuthorizationRequestRepository</code> với một Redis repository độc lập: repository này vẫn truy cập giao diện <code>HttpSession</code>; chính **Spring Session** có thể thay đổi cách dữ liệu HTTP session được lưu phía dưới.

Cần chú ý khả năng serialize của object trong session, độ trễ, timeout và hành vi cập nhật đồng thời khi dùng distributed session. Nếu bổ sung custom attributes vào authorization request, chúng cũng phải phù hợp với cách lưu trữ session.

## 10. Nhiều filter chain: start và callback phải vào đúng chain

Spring Security Servlet có thể có nhiều <code>SecurityFilterChain</code>. <code>FilterChainProxy</code> chọn **chain đầu tiên** có matcher phù hợp. Nếu start URL và callback URL vào các chain không có cấu hình OAuth2 Login tương thích, luồng có thể thất bại trước cả khi repository được gọi.

Ví dụ dễ gặp:

~~~java
http
    .securityMatcher("/app/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

Chain này không match các endpoint mặc định:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

Vì vậy, chỉ có <code>oauth2Login()</code> bên trong chain không đủ nếu chain không bao phủ URL hạ tầng đăng nhập.

### 10.1. Thiết kế API chain và Web chain

Ví dụ triển khai API tách khỏi web:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultipleChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        // Web chain bắt mọi URL còn lại, gồm start và callback.
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ cần thêm resource-server dependency và JWT decoder/issuer cấu hình hợp lệ cho API nếu muốn chạy API bearer token. Web OAuth2 Login vẫn cần OAuth2 Client dependency và ClientRegistration. Hai loại cấu hình phục vụ các vai trò bảo mật khác nhau.

Ở đây:

| Request | Chain đầu tiên match | Mục tiêu |
|---|---|---|
| <code>/api/orders</code> | API <code>@Order(1)</code> | Xác thực bằng bearer JWT |
| <code>/oauth2/authorization/company</code> | Web <code>@Order(2)</code> | Lưu authorization request, redirect tới IdP |
| <code>/login/oauth2/code/company</code> | Web <code>@Order(2)</code> | Tải/xóa authorization request, xử lý code và state |
| <code>/dashboard</code> | Web <code>@Order(2)</code> | Phục vụ người dùng đã đăng nhập |

Nếu web chain có <code>securityMatcher</code> hẹp, phải bao gồm cả authorization start endpoint, callback, trang login và các URL liên quan. Chỉ thêm <code>.requestMatchers("/login/oauth2/code/**").permitAll()</code> trong <code>authorizeHttpRequests</code> không giúp callback đi vào chain nếu <code>securityMatcher</code> đã loại request từ đầu.

### 10.2. Không biến Web OAuth2 Login thành stateless tùy tiện

API chỉ dùng bearer JWT thường phù hợp với <code>SessionCreationPolicy.STATELESS</code>. Nhưng OAuth2 Login Servlet mặc định cần giữ authorization request qua browser redirect. Nếu web chain bị cấu hình <code>STATELESS</code> và không có giải pháp lưu state thay thế được thiết kế rõ ràng, việc giữ session và hoàn tất authentication có thể không còn hoạt động như kỳ vọng.

Không suy ra rằng <code>STATELESS</code> làm <code>HttpSessionOAuth2AuthorizationRequestRepository</code> tự đổi sang storage khác. Chính repository này lưu vào HttpSession; kiến trúc không session đòi hỏi chủ động thay đổi cách lưu authorization request và authentication, kèm đánh giá bảo mật.

## 11. Repository tùy biến khi cần nhiều authorization request song song

Mặc định một request/session là đủ cho nhiều ứng dụng, nhưng không luôn phù hợp khi người dùng mở nhiều tab, đổi provider liên tiếp, hoặc một luồng đăng nhập có thể đang chờ trong khi luồng khác bắt đầu.

Một hướng mở rộng là lưu **Map theo state** trong HTTP session:

~~~text
session["PENDING_AUTHORIZATION_REQUESTS"] =
    {
      "state-A": OAuth2AuthorizationRequest-A,
      "state-B": OAuth2AuthorizationRequest-B,
      ...
    }
~~~

Triển khai custom <code>AuthorizationRequestRepository<OAuth2AuthorizationRequest></code> có thể theo nguyên tắc:

~~~text
save(request):
    kiểm tra request.state tồn tại
    lấy map của session, hoặc tạo mới
    thêm một entry với key = request.state
    ghi lại map vào session

load(callback):
    lấy state từ callback
    chỉ truy cập map của đúng session
    trả request có key đúng state, nếu tồn tại

remove(callback):
    lấy request có key đúng state của session
    xóa riêng entry đó
    trả request đã xóa
~~~

Đây là thiết kế khái niệm, không phải mã triển khai production. Khi tự xây:

- State phải đủ ngẫu nhiên và duy nhất cho từng authorization request.
- Không chấp nhận state tùy ý từ callback để tạo request mới.
- Không làm mất các thuộc tính PKCE verifier, nonce, registration ID và các dữ liệu cần cho token exchange.
- Xóa entry khi dùng và dọn entry hết hạn để tránh tích lũy trong session.
- Giới hạn số lượng pending requests mỗi session; không để người dùng vô hạn tạo authorization requests nhằm chiếm bộ nhớ.
- Xử lý cập nhật đồng thời giữa tab/request và tương thích với distributed session nếu triển khai nhiều node.
- Tránh log map vì authorization request có thể chứa thông tin nhạy cảm.

Không cần repository tùy biến chỉ vì ứng dụng dùng nhiều provider: một session vẫn có thể đăng nhập theo từng lần; nhu cầu tùy biến phát sinh khi muốn nhiều **lượt authorization đang chờ đồng thời** hoặc quản lý trạng thái khác mặc định.

### 11.1. Vì sao không đặt toàn bộ request trong cookie?

Một số ví dụ trực tuyến thay HTTP session bằng cookie chứa serialized authorization request. Cách này cần cân nhắc kỹ:

- Nếu cookie có verifier, nonce hoặc dữ liệu nhạy cảm, phải bảo vệ bí mật và toàn vẹn; base64 không phải mã hóa.
- Cookie có giới hạn kích thước và chịu các quy tắc domain, path, SameSite, Secure, HttpOnly.
- Phải ngăn client sửa dữ liệu nhằm thay redirect URI, registration ID hoặc attributes.
- Cần ràng buộc thời hạn, dọn cookie sau callback và xem xét nhiều tab/các cookie trùng tên.

Một repository dựa trên cookie được thiết kế thiếu chặt chẽ có thể tạo rủi ro bảo mật lớn hơn vấn đề session ban đầu. Trong ứng dụng Servlet thông thường, ưu tiên HTTP session hoặc cơ chế lưu trạng thái phía server đã được bảo vệ.

## 12. Phân biệt với các repository/service khác trong Spring Security

Các thành phần có tên tương tự nhưng lưu những dữ liệu khác nhau:

| Thành phần | Dữ liệu lưu/tra cứu | Vòng đời |
|---|---|---|
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | Authorization request đang chờ callback | Từ authorization redirect đến callback hoặc timeout |
| <code>ClientRegistrationRepository</code> | Metadata Client và provider như client ID, endpoints, scopes | Thường suốt thời gian ứng dụng chạy |
| <code>OAuth2AuthorizedClientRepository</code> | Authorized client gắn với principal/request, gồm token đã cấp | Sau khi token exchange hoàn thành |
| <code>OAuth2AuthorizedClientService</code> | Authorized clients theo registration/principal, thường cho service-layer | Theo chính sách persistence/token |
| <code>SecurityContextRepository</code> | SecurityContext chứa Authentication của request/user | Giữa các request, tùy chiến lược session/context |
| <code>RequestCache</code> | Saved request mà người dùng muốn truy cập trước khi login | Hữu ích để redirect người dùng về trang đích sau login |

Ví dụ: người dùng ban đầu truy cập <code>/dashboard</code> rồi được chuyển tới IdP. <code>RequestCache</code> có thể nhớ trang <code>/dashboard</code> để trở về sau login; **<code>HttpSessionOAuth2AuthorizationRequestRepository</code> nhớ authorization request cùng state** để xử lý callback. Hai cơ chế có thể đều dùng session nhưng không giải quyết cùng một vấn đề.

Tương tự, hoàn thành callback không có nghĩa authorization request phải được giữ lại để tái sử dụng access token. Token được quản lý qua authorized client components nếu ứng dụng có nhu cầu lưu và sử dụng token trong các request tiếp theo.

## 13. Chẩn đoán sự cố callback và correlation

### 13.1. Từ biểu hiện đến nguyên nhân

| Biểu hiện | Nguyên nhân cần xem | Cách xử lý |
|---|---|---|
| <code>authorization_request_not_found</code> hoặc lỗi tương đương | Callback không tìm được request theo session/state | Kiểm tra cùng session cookie, state, repository và chain |
| Login thành công tại OP nhưng callback 404 | URL callback không vào chain có <code>OAuth2LoginAuthenticationFilter</code> hoặc filter processing URI không khớp | Kiểm tra redirect URI, securityMatcher, filter chain order |
| Callback 401/403 | API/basic chain chặn request, authorization rule hoặc request method/CSRF không phù hợp | Tìm chain khớp đầu tiên, kiểm tra policy của callback |
| Login lần đầu được, mở tab thứ hai thì tab đầu lỗi | Request sau ghi đè request trước trong session | Giới hạn flow đồng thời hoặc dùng repository theo state nhiều entry |
| Lỗi ngẫu nhiên khi chạy nhiều instance | HTTP session không dùng chung, routing hoặc session persistence không đồng nhất | Kiểm tra sticky session/Spring Session/session store |
| Callback có state hợp lệ nhưng repository load trả <code>null</code> | Mất session, state khác hoặc session đã lưu request mới | Xác nhận cookie/session ID và vòng đời request |
| Token endpoint trả <code>invalid_grant</code> sau khi callback được nhận | Code hết hạn/đã dùng, redirect URI/PKCE sai | Kiểm tra token exchange sau khi xác nhận correlation |
| Đăng nhập xong trang đích vẫn anonymous | SecurityContext không được lưu/đọc như mong đợi hoặc chain trang đích khác chính sách | Kiểm tra SecurityContextRepository, session và chain của trang đích |
| Callback cross-site POST không có cookie | Cookie SameSite hoặc CSRF/method policy không phù hợp với <code>form_post</code> | Đánh giá callback method, cookie policy và bảo vệ CSRF có kiểm soát |
| Đăng nhập OIDC báo issuer/nonce mismatch | ID Token không khớp OP/authorization request | Kiểm tra issuer, registration, nonce và validation của thư viện |

### 13.2. Thứ tự tìm lỗi thực tế

Khi gặp lỗi callback, nên xem những điểm theo đúng quan hệ phụ thuộc:

1. **URL callback thực tế:** host, scheme, path, registration ID và phương thức HTTP.
2. **SecurityFilterChain:** request callback match chain nào đầu tiên; chain đó có OAuth2 Login filter không?
3. **HTTP session:** browser có gửi session cookie giống lượt bắt đầu login; session còn tồn tại trên node nhận callback không?
4. **State:** callback có state và state có tương ứng authorization request đang lưu không?
5. **Repository:** start và callback có dùng cùng repository và cùng key/lưu trữ không?
6. **PKCE/nonce:** authorization request có giữ được attributes cần dùng đến khi token exchange không?
7. **Provider response:** authorization code còn hiệu lực, redirect URI hợp lệ và token/ID Token được xác minh đúng không?

Một lỗi ở bước đầu có thể che khuất những bước sau. Ví dụ nếu callback bị API chain bắt, repository web có thể hoàn toàn không được gọi; chưa nên kết luận là sai state.

### 13.3. Bật log phục vụ quan sát

Trong môi trường phát triển, có thể tạm bật log Spring Security liên quan:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.oauth2.client: DEBUG
~~~

Mức log và tên category có thể thay đổi theo phiên bản. Dùng log để quan sát chain/filter và loại lỗi, nhưng **không ghi nguyên authorization code, state, PKCE verifier, client secret, access token, refresh token hoặc ID Token** vào log, ticket, công cụ phân tích hay ảnh chụp màn hình. Các giá trị đó có thể nhạy cảm hoặc dùng được trong khoảng thời gian ngắn.

Nếu thêm log ứng dụng quanh flow, chỉ ghi registration ID, tên endpoint, request correlation ID an toàn, trạng thái thành công/thất bại và mã lỗi đã loại bỏ bí mật. Không cần log nội dung nguyên bản của <code>OAuth2AuthorizationRequest</code>.

## 14. Các hiểu lầm thường gặp

**“Callback có state thì chắc chắn hợp lệ.”** Không. State phải đối chiếu được với authorization request đã lưu trong **đúng session**; một chuỗi state tự gửi từ client không đủ.

**“Repository lưu authorization code và token.”** Không. Nó lưu request ban đầu. Authorization code nằm trong callback, còn token được xử lý sau token exchange qua các component khác.

**“Chỉ cần bật oauth2Login là không bao giờ mất session.”** Không. Cookie policy, session timeout, load balancer, reverse proxy và nhiều tab có thể làm mất hoặc ghi đè authorization request.

**“Hai tab đăng nhập không ảnh hưởng nhau vì state khác nhau.”** Không phải với implementation mặc định dùng một request hiện hành trong session. Tab mở sau có thể ghi đè request tab trước.

**“Đổi sang STATELESS cho toàn bộ ứng dụng giúp OAuth2 Login đơn giản hơn.”** Không. HTTP session là cơ chế mặc định để giữ authorization request giữa hai lần redirect trong Servlet; thay đổi cần thiết kế lưu trạng thái khác và cách duy trì authentication.

**“Chỉ cần thêm permitAll cho callback.”** Không. Request phải thuộc chain có OAuth2 Login filter, rồi mới đến quy tắc authorization. <code>securityMatcher</code> và thứ tự chain quyết định điều này.

**“PKCE verifier có thể lấy lại từ code_challenge.”** Không. Với S256 và verifier ngẫu nhiên mạnh, challenge được dẫn xuất một chiều. Client phải giữ verifier gốc trong trạng thái authorization request đến token exchange.

## 15. Bài tập và tình huống thực hành

### Tình huống A: callback từ phiên khác

Trình duyệt A bắt đầu login và có session <code>S1</code>, state <code>V1</code>. Một trình duyệt B gửi callback chứa đúng chuỗi <code>V1</code> nhưng không có cookie của <code>S1</code>.

**Câu hỏi:** Repository có tìm được authorization request không?

**Đáp án:** Không. Repository dựa trên HTTP session; B không có session chứa request của A. Ngay cả khi biết state, B vẫn không sở hữu trạng thái authorization request tương ứng trong session của A.

### Tình huống B: hai tab dùng chung session

~~~text
Tab A: state=A, lưu request A vào session
Tab B: state=B, lưu request B vào cùng session
Tab A: callback state=A
~~~

**Câu hỏi:** Điều gì dễ xảy ra với implementation mặc định?

**Đáp án:** Request B có thể đã thay thế request A. Callback của A không tìm được request có state A, nên authentication không thể tiếp tục. Nếu nhiều authorization attempt đồng thời là yêu cầu nghiệp vụ, cân nhắc custom repository keyed by state.

### Tình huống C: PKCE bị mất khi chuyển repository

Nhóm phát triển thay session repository bằng cơ chế chỉ lưu JSON chứa <code>state</code> và <code>redirectUri</code>. Callback có state khớp nhưng token endpoint từ chối code.

**Giải thích:** Nếu Client dùng PKCE, <code>code_verifier</code> và các thuộc tính cần cho token exchange có thể bị mất khi rút gọn serialization. Custom repository phải bảo toàn đầy đủ authorization request và thông tin liên quan cho flow.

### Tình huống D: API chain chiếm callback

~~~text
@Order(1): securityMatcher("/login/**", "/api/**"), httpBasic()
@Order(2): securityMatcher("/app/**", "/login/oauth2/code/**"), oauth2Login()
~~~

**Câu hỏi:** Callback <code>/login/oauth2/code/company</code> thuộc chain nào?

**Đáp án:** Chain đầu tiên với <code>/login/**</code> match trước, nên chain chứa OAuth2 Login không được chọn. Cần giới hạn matcher của chain đầu hoặc thiết kế lại ưu tiên chain để start và callback thuộc đúng luồng.

### Bài thực hành: quan sát vòng đời session request

1. Tạo một Spring Boot Servlet web app có <code>spring-boot-starter-oauth2-client</code> và một ClientRegistration OIDC thử nghiệm.
2. Bật <code>oauth2Login()</code>; truy cập <code>/oauth2/authorization/{registrationId}</code>.
3. Quan sát response redirect và sự tồn tại của cookie session mà không sao chép giá trị bí mật vào log.
4. Hoàn tất đăng nhập qua OP và xác định callback có dùng đúng session.
5. Dùng Mock Servlet example để gọi <code>saveAuthorizationRequest</code>, <code>loadAuthorizationRequest</code> và <code>removeAuthorizationRequest</code>; quan sát request biến mất sau remove.
6. Thử callback với state khác hoặc một session khác trong môi trường test; giải thích vì sao load trả <code>null</code>.
7. Thử hai lần bắt đầu đăng nhập trong cùng session trước khi hoàn tất lần đầu và quan sát ảnh hưởng của request được lưu sau.

Các bài thực hành tập trung vào **correlation và vòng đời authorization request**. Việc kiểm thử OAuth2/OIDC end-to-end cần Authorization Server thử nghiệm phù hợp để cấp code và token thật theo giao thức.

## 16. Tóm lược kiến thức

- **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>** là implementation mặc định trên Servlet dùng HTTP session để lưu <code>OAuth2AuthorizationRequest</code> giữa authorization redirect và callback.
- <code>OAuth2AuthorizationRequestRedirectFilter</code> lưu request trước khi chuyển tới IdP; <code>OAuth2LoginAuthenticationFilter</code> lấy/xóa request khi callback quay về và dùng nó để tiếp tục authentication.
- Correlation phụ thuộc vào **đúng HTTP session và đúng state**. PKCE verifier cùng dữ liệu liên quan phải được giữ nguyên nếu flow sử dụng PKCE.
- Implementation mặc định thường giữ **một authorization request tại một thời điểm trong session**; nhiều tab đăng nhập đồng thời có thể ghi đè trạng thái.
- Callback phải nằm trong **SecurityFilterChain có OAuth2 Login filter**, cookie/session phải được browser gửi lại và tồn tại trên node nhận callback.
- Nếu thay repository, phải duy trì đầy đủ thông tin authorization request, bảo vệ dữ liệu, xử lý trạng thái dùng một lần, hết hạn và cập nhật đồng thời.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Login (Servlet):** authorization endpoint, redirection endpoint, authorization request repository và login filters.
- **Spring Security Java API — <code>HttpSessionOAuth2AuthorizationRequestRepository</code> và <code>AuthorizationRequestRepository</code>:** hợp đồng <code>load</code>, <code>save</code>, <code>remove</code>.
- **Spring Security Java API — <code>OAuth2AuthorizationRequestRedirectFilter</code> và <code>OAuth2LoginAuthenticationFilter</code>:** các điểm sử dụng authorization request repository.
- **Spring Security Reference — Servlet Architecture:** <code>FilterChainProxy</code>, <code>SecurityFilterChain</code> và matcher selection.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization request, <code>state</code>, authorization response và authorization code grant.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code verifier/challenge và trao đổi authorization code an toàn hơn.
- **OpenID Connect Core 1.0:** authorization code flow, nonce và quy tắc xác minh ID Token.
