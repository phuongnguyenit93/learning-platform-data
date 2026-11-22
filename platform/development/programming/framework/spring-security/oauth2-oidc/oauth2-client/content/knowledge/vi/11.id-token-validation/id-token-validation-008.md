# 11.8. Đối chiếu nonce với authorization request ban đầu

## 1. Vì sao ID Token có chữ ký hợp lệ vẫn cần kiểm tra nonce?

Khi một ứng dụng **Spring Security OAuth 2.0 OIDC Client** cho người dùng đăng nhập qua OpenID Connect (OIDC), nhà cung cấp danh tính (*OpenID Provider*, OP) có thể phát hành **ID Token** đã được ký số. Client có thể kiểm tra chữ ký, issuer, audience và thời hạn của token để xác nhận token do đúng nhà cung cấp cấp cho ứng dụng.

Nhưng hãy xét tình huống sau:

- Người dùng bắt đầu một lần đăng nhập mới từ trình duyệt.
- Có một ID Token được phát hành trong **giao dịch cũ** nhưng vẫn còn thời hạn.
- Nếu client chỉ dựa vào chữ ký và các claim tĩnh, token cũ có thể trông hoàn toàn hợp lệ.
- Client cần ràng buộc ID Token nhận được với **authorization request cụ thể vừa khởi tạo**, thay vì chỉ với một issuer/client nói chung.

Đây là vai trò của **`nonce`** (*number used once*): một giá trị khó đoán do OIDC client đưa vào yêu cầu xác thực; khi phát hành ID Token, OP đưa giá trị tương ứng vào claim `nonce`. Client đối chiếu nó với ngữ cảnh đã lưu từ lúc bắt đầu giao dịch.

**Điểm cốt lõi:** chữ ký trả lời “ID Token này do ai phát hành và có bị sửa không?”; nonce trả lời “ID Token này có được phát hành cho **lượt yêu cầu xác thực đang được xử lý** không?” Hai câu hỏi bổ sung cho nhau.

Trong thực hành, không được xem nonce là cơ chế bảo mật duy nhất. Nó phải hoạt động cùng `state`, Authorization Code + PKCE, xác minh ID Token, HTTPS và cách quản lý session đúng đắn.

## 2. Nonce là gì trong OpenID Connect?

### 2.1. Nonce xuất hiện ở hai phía của giao dịch

Một yêu cầu authorization của OIDC client có thể chứa:

~~~http
GET /authorize?response_type=code
    &client_id=portal-web
    &scope=openid%20profile
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    &state=STATE_RANDOM_VALUE
    &nonce=NONCE_RANDOM_VALUE
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: id.example.com
~~~

Request trên được xuống dòng để minh họa; URL thật phải được mã hóa hợp lệ. Client lưu giá trị nonce hoặc đủ dữ liệu để khôi phục giá trị **được gửi thực sự** cho OP.

Sau bước đổi authorization code, token endpoint trả phản hồi OIDC có `id_token`. Payload ID Token được giải mã có thể chứa:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "subject-3c91",
  "aud": "portal-web",
  "exp": 1925003600,
  "iat": 1925000000,
  "nonce": "NONCE_RANDOM_VALUE"
}
~~~

**Client chỉ được chấp nhận claim `nonce` sau khi token đã được xử lý/xác minh theo yêu cầu OIDC**; việc Base64URL-decode payload không phải là kiểm tra bảo mật.

### 2.2. Điều kiện đối chiếu

Tư duy kiểm tra:

~~~text
Authorization request ban đầu:
  nonce gửi tới OP = "N-ABC"
  state gửi tới OP = "S-123"
  registration = "company"

Callback và token exchange:
  state trả về = "S-123"
  ID Token đã xác minh có nonce = "N-ABC"

=> Nonce khớp giao dịch vừa khởi tạo.
~~~

Ngược lại:

~~~text
Authorization request ban đầu:
  nonce = "N-ABC"

ID Token nhận về:
  nonce = "N-OLD"

=> Không khớp. Từ chối xác thực OIDC cho giao dịch này.
~~~

Nếu client đã gửi nonce trong request, nó **phải kiểm tra** claim nonce tương ứng trong ID Token. Một ID Token thiếu nonce hoặc có nonce khác giá trị cần đối chiếu không được chấp nhận trong giao dịch đó.

### 2.3. Nonce có bắt buộc ở mọi luồng OIDC không?

OIDC Core quy định cách dùng nonce theo **response type/flow**:

| Luồng | Vai trò của nonce |
| --- | --- |
| **Authorization Code flow** (`response_type=code`) | Tham số `nonce` là **tùy chọn theo OIDC Core**; nếu client gửi thì phải kiểm tra claim tương ứng trong ID Token |
| **Implicit flow** (ID Token trả qua front channel) | Nonce là thành phần cần thiết theo các yêu cầu của flow tương ứng để ràng buộc ID Token |
| **Hybrid flow** | Các yêu cầu cụ thể phụ thuộc response type và ID Token được trả ở front channel hay token endpoint |

Bài học tập trung vào **Spring Security Servlet OIDC Login với Authorization Code flow**, thường kết hợp PKCE. Dù `nonce` không phải tham số bắt buộc của mọi Authorization Code request theo chuẩn, việc dùng nonce là lớp bảo vệ bổ sung hữu ích; khi đã dùng thì **tuyệt đối không được bỏ qua bước xác minh**.

Không lấy quy tắc của Implicit/Hybrid rồi khẳng định tất cả Authorization Code requests thiếu nonce đều không hợp lệ. Ngược lại, cũng không viện lý do nonce tùy chọn trong Code flow để bỏ kiểm tra nonce đã được gửi.

## 3. Phân biệt nonce, state, PKCE và authorization code

Các giá trị này thường cùng xuất hiện trong một giao dịch đăng nhập nhưng bảo vệ các ranh giới khác nhau.

| Giá trị | Được tạo/gửi ở đâu? | Kiểm tra ở đâu? | Mục đích |
| --- | --- | --- | --- |
| `state` | Client gửi trong authorization request; OP trả ở authorization response | Client xử lý callback | Liên kết callback với yêu cầu trước đó; giúp phòng ngừa authorization response/login CSRF |
| `nonce` | Client gửi trong OIDC authorization request; OP phản ánh trong **ID Token** | OIDC client sau khi nhận ID Token | Gắn ID Token với **authentication request cụ thể**; chống một số kiểu phát lại |
| `code_verifier` / `code_challenge` (PKCE) | Client giữ verifier, gửi challenge khi authorize | Token endpoint xác minh verifier khi đổi code | Ràng buộc authorization code với bên khởi tạo PKCE |
| Authorization code | OP trả cho browser trong callback thành công | Token endpoint nhận code qua backend | Đổi lấy token; ngắn hạn và sử dụng một lần |
| Client session cookie | Browser gửi về ứng dụng | Servlet/session infrastructure | Tìm ngữ cảnh người dùng và authorization request đang chờ |

### 3.1. Ba loại correlation, ba câu hỏi

~~~text
state:
  "Callback này có phải phản hồi cho authorization request đã lưu?"

PKCE:
  "Bên đổi authorization code có giữ code_verifier đúng không?"

nonce:
  "ID Token này có tương ứng với OIDC authentication request ấy không?"
~~~

**Không tráo đổi mục đích:** `state` không thay cho nonce; nonce không thay việc đối chiếu state; PKCE không thay kiểm tra chữ ký, issuer và audience của ID Token.

### 3.2. Đừng dùng cùng một chuỗi cho mọi tham số

Về mặt thiết kế, nên sinh các giá trị ngẫu nhiên, độc lập cho state, nonce và PKCE verifier, do framework hoặc thư viện bảo mật tin cậy quản lý. Không dùng một chuỗi cố định như `nonce=login`, timestamp, email hoặc ID người dùng. Những giá trị dễ đoán không cung cấp ràng buộc giao dịch đáng tin cậy.

### 3.3. Nonce không phải access token hay session ID

Nonce **không cấp quyền gọi API**, không chứng minh người dùng có role nào và không phải khóa session được dùng để truy cập dữ liệu người dùng. Nonce có thể xuất hiện trong URL authorization gửi qua browser; không nên nhét secret của ứng dụng, dữ liệu cá nhân hoặc claim nhạy cảm vào đó.

## 4. Luồng end-to-end: lưu nonce trước redirect, kiểm tra sau token exchange

Một ứng dụng OIDC Servlet cần duy trì kết nối giữa **request trước redirect** và **ID Token sau callback**:

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Boot Servlet OIDC Client
    participant R as AuthorizationRequestRepository
    participant OP as OpenID Provider
    B->>C: GET /oauth2/authorization/company
    C->>C: Tạo state, nonce, PKCE context
    C->>R: Lưu OAuth2AuthorizationRequest
    C-->>B: 302 tới authorization endpoint (state, nonce, challenge)
    B->>OP: Đăng nhập / consent
    OP-->>B: 302 callback code + state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>R: Lấy/tiêu thụ request ban đầu
    C->>C: Kiểm tra state, registration và callback
    C->>OP: POST token endpoint (code + PKCE verifier)
    OP-->>C: access_token + id_token
    C->>C: Xác minh chữ ký, iss, aud, exp, nonce
    alt Nonce khớp
        C-->>B: Thiết lập Authentication/session hợp lệ
    else Nonce thiếu hoặc sai
        C-->>B: Authentication failure; không đăng nhập mới
    end
~~~

Thứ tự triển khai nội bộ của từng bộ lọc có thể khác theo phiên bản; sơ đồ mô tả **ràng buộc logic**. Khóa JWKS có thể đã được cache thay vì được tải lại cho mỗi ID Token.

### 4.1. Chặng đi: tạo authorization request

Khi người dùng truy cập:

~~~text
/oauth2/authorization/company
~~~

Spring Security dùng `ClientRegistrationRepository` chọn registration `company` và xây dựng `OAuth2AuthorizationRequest`. Đối với OIDC, các tham số có thể gồm `scope=openid`, `state`, `nonce` và PKCE khi bật/được hỗ trợ.

Một dạng mô hình:

~~~text
OAuth2AuthorizationRequest
  authorizationUri: https://id.example.com/authorize
  clientId: portal-web
  responseType: code
  redirectUri: https://portal.example.com/login/oauth2/code/company
  scopes: [openid, profile, email]
  state: random-state-1
  additionalParameters:
    nonce: value-sent-to-provider
    code_challenge: ...
    code_challenge_method: S256
  attributes:
    registration_id: company
    nonce_context: data-for-verification
    code_verifier: secret-for-PKCE
~~~

Đây **không phải cấu trúc serialization cố định**. Spring Security có thể lưu nonce gốc hoặc dữ liệu để tính/đối chiếu nonce trong `attributes`; tên khóa nội bộ và cách biểu diễn tùy phiên bản.

### 4.2. Chặng về: phục hồi đúng request

Khi browser quay lại callback, Spring Security cần tìm lại authorization request trước đó. Với Servlet OAuth2 Login thông thường, `HttpSessionOAuth2AuthorizationRequestRepository` lưu request trong HTTP session, còn session cookie giúp server xác định session ban đầu.

Client kiểm tra `state` và ngữ cảnh client trước khi xử lý token. Khi có ID Token:

1. Xác định issuer đáng tin cậy và cấu hình client registration.
2. Kiểm tra chữ ký/thuật toán hoặc các yêu cầu mã hóa tương ứng.
3. Đối chiếu `iss`, `aud`, `azp` nếu áp dụng, `exp` và các điều kiện OIDC khác.
4. Nếu authorization request đã gửi nonce, tính/lấy **expected nonce** đúng cách từ request đã lưu.
5. So sánh với claim `nonce` của ID Token.
6. Chỉ tạo kết quả đăng nhập OIDC khi các điều kiện bắt buộc đều đạt.

Nếu không phục hồi được authorization request, ứng dụng **không có ngữ cảnh tin cậy để đối chiếu nonce**. Không được “cứ nhận ID Token vì chữ ký đúng” rồi bỏ qua correlation.

### 4.3. Vì sao cần tiêu thụ yêu cầu một lần?

Authorization Code vốn phải ngắn hạn và sử dụng một lần. Client cũng cần loại bỏ hoặc đánh dấu request chờ đã được xử lý, tránh cùng một authorization request bị sử dụng như giao dịch mới nhiều lần.

Nonce hỗ trợ chống phát lại nhưng không tự thay thế **single-use authorization code**, **state check**, TTL của session và chính sách tiêu thụ authorization request. Nếu một callback bị phát lại, framework nên từ chối khi request đã bị tiêu thụ hoặc code không còn hợp lệ.

## 5. Sinh nonce an toàn

### 5.1. Nonce cần có những tính chất gì?

Một nonce dùng để bảo vệ giao dịch nên:

- Được sinh bởi **cryptographically secure random number generator (CSPRNG)**.
- Có entropy đủ lớn để không thể dự đoán thực tế; trong ứng dụng mới có thể chọn ít nhất 128 bit entropy.
- Khác nhau giữa các yêu cầu xác thực độc lập.
- Không chứa mật khẩu, email, user ID hoặc bí mật cấu hình.
- Được lưu hoặc ràng buộc an toàn đủ lâu để kiểm tra callback nhưng không giữ vô thời hạn.
- Được so sánh với **nonce đã gửi cho OP**, không phải một giá trị client tự suy đoán khi callback đến.

Ví dụ Java **chỉ minh họa cách sinh nonce**:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String randomNonce() {
        byte[] bytes = new byte[32]; // 256 bit entropy
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
~~~

Ví dụ không phải yêu cầu tự triển khai nonce generator khi đã dùng Spring Security; framework thường cung cấp cơ chế phù hợp. Giá trị được URL-safe Base64 encode là một chuỗi ngẫu nhiên, **không phải JWT**.

### 5.2. Nonce có thể được biến đổi trước khi gửi không?

Một điểm dễ gây nhầm trong quá trình debug: **cách lưu nonce nội bộ** và **giá trị `nonce` xuất hiện trên URL authorization** có thể không giống nguyên văn.

Một số cách triển khai giữ một giá trị nonce ngẫu nhiên trong thuộc tính nội bộ nhưng gửi **giá trị băm** của nó cho provider, sau đó tính lại giá trị mong đợi để so khớp với claim `nonce` của ID Token. Ví dụ minh họa:

~~~text
client_internal_nonce = random-256-bit-value
nonce_sent_to_provider = BASE64URL(SHA-256(client_internal_nonce))

Authorization request:
  nonce = nonce_sent_to_provider

ID Token claim:
  nonce = nonce_sent_to_provider

Client:
  expected = BASE64URL(SHA-256(saved_internal_nonce))
  compare expected with id_token.nonce
~~~

Điều quan trọng không phải client luôn phải băm nonce: **OIDC yêu cầu claim nonce phù hợp với giá trị đã được đưa vào Authentication Request**. Việc băm hay không là lựa chọn triển khai; nếu Spring Security đang làm giúp việc này, ứng dụng không được tự so claim với một giá trị nội bộ khác biểu diễn rồi kết luận sai.

**Không thiết kế custom validator “cứ lấy request.attributes.nonce so trực tiếp với token.nonce” nếu chưa hiểu cách request resolver của phiên bản Spring Security đã tạo nonce.** An toàn hơn là để OIDC authentication provider của Spring Security thực hiện xác minh.

### 5.3. So sánh nonce an toàn

Về nguyên tắc, phải so sánh **chuỗi mong đợi chính xác** với chuỗi claim của ID Token, không so sánh gần đúng hoặc bỏ qua khoảng trắng, không tự cắt prefix hay đổi chữ hoa/chữ thường. Nếu tự triển khai một protocol handler đặc biệt, dùng cơ chế so sánh thích hợp cho giá trị bảo mật và tránh tiết lộ secret qua log/exception.

Không dùng:

~~~java
// PHẢN VÍ DỤ — tuyệt đối không dùng:
if (idTokenNonce != null) {
    acceptLogin(); // Chỉ kiểm tra có nonce, không kiểm tra giá trị!
}
~~~

Và không dùng:

~~~java
// PHẢN VÍ DỤ — không tin giá trị mong đợi từ browser:
String expected = request.getParameter("nonce");
if (expected.equals(idTokenNonce)) {
    acceptLogin();
}
~~~

**Expected nonce** phải xuất phát từ authorization request/binding **đã được client lưu một cách đáng tin cậy**, không từ tham số mới do browser tự gửi ở callback.

## 6. AuthorizationRequestRepository giữ ngữ cảnh nonce như thế nào?

### 6.1. Repo là cầu nối giữa hai HTTP requests

Trong Spring Security Servlet, `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` có nhiệm vụ lưu, truy xuất và tiêu thụ authorization request chờ callback. Các phương thức:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository;

repository.saveAuthorizationRequest(authRequest, request, response);

OAuth2AuthorizationRequest pending =
    repository.loadAuthorizationRequest(request);

OAuth2AuthorizationRequest consumed =
    repository.removeAuthorizationRequest(request, response);
~~~

Đoạn này diễn giải API; biến `authRequest`, `request` và `response` được giả định đã có trong một luồng Servlet. Với cấu hình mặc định, Spring Security gọi các phương thức cần thiết; ứng dụng **không cần tự gọi repository ở controller**.

Repository phải giữ nguyên **các thuộc tính cần cho callback**: state, registration/context, redirect URI, PKCE verifier và dữ liệu nonce khi có. Một custom implementation chỉ lưu state rồi bỏ `additionalParameters`/`attributes` có thể khiến xác minh nonce hoặc PKCE thất bại.

### 6.2. HttpSessionOAuth2AuthorizationRequestRepository

Spring Security Servlet OAuth2 Login thường dùng:

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;

HttpSessionOAuth2AuthorizationRequestRepository repository =
    new HttpSessionOAuth2AuthorizationRequestRepository();
~~~

Lúc chặng đi:

~~~text
Browser B
  Cookie: JSESSIONID=S123

Application HTTP Session S123
  pending OAuth2AuthorizationRequest
    state: S-NEW
    nonce context: N-NEW
    PKCE context: V-NEW
    registration: company
~~~

Lúc chặng về, browser cần mang đúng cookie session. Nếu cookie bị mất, sai domain/path, session hết hạn hoặc callback đến node không đọc được session, framework không thể khôi phục request và không thể xác minh correlation như mong đợi.

**Đừng sửa bằng cách tắt kiểm tra state/nonce hoặc chấp nhận ID Token khi request không tồn tại.** Thay vào đó, tìm nguyên nhân session bị mất, cấu hình cookie/proxy hay kiến trúc lưu trữ.

### 6.3. Session nhiều node và nhiều tab

| Trường hợp | Rủi ro | Giải pháp thiết kế |
| --- | --- | --- |
| Một instance Spring Boot | Session ở memory thường đủ cho demo | Bảo vệ session cookie và TTL |
| Nhiều instance sau load balancer | Chặng đi ở node A, chặng về ở node B không thấy request | Spring Session/shared store hoặc routing session có kiểm soát |
| Người dùng login ở hai tab | Pending request có thể bị thay bởi request mới, tùy repository | Nếu sản phẩm yêu cầu concurrency, dùng repository có hỗ trợ nhiều state trong cùng session |
| Người dùng mất nhiều phút ở IdP | Session/request chờ hết hạn | Hiển thị login failure và cho bắt đầu lại |
| Callback bị phát lại | Authorization request đã bị tiêu thụ hoặc code hết hạn | Từ chối, không tự khôi phục request cũ |

Nếu custom repository dùng Redis hoặc database để lưu nhiều request, khóa tra cứu phải ràng buộc **state và browser/session context**, có TTL và hành vi tiêu thụ một lần. Chỉ lưu theo state trong kho dùng chung không bảo đảm tránh nhầm giao dịch giữa các browser.

### 6.4. Không log nonce hay trạng thái callback

Trong khi debug, có thể cần biết “có nonce hay không”, “repository tìm thấy request hay không” hoặc “nonce validation thất bại” nhưng **không nên log giá trị nonce, state, PKCE verifier, authorization code, token, cookie session**.

Ví dụ log metadata an toàn:

~~~text
event=oidc_login_failure
registration_id=company
stage=id_token_validation
reason=nonce_mismatch
correlation_id=internal-trace-7b12
~~~

`reason=nonce_mismatch` là mã minh họa dành cho hệ thống log, không đảm bảo trùng chính xác mã exception của mọi phiên bản Spring Security. `correlation_id` phải độc lập với credential OAuth/OIDC.

## 7. Tích hợp Spring Security Servlet OIDC Client

### 7.1. Dependency

Một ứng dụng Spring Boot 3.x dùng Servlet MVC và OIDC Login có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Với Spring Boot 4.x, các tên starter được modular hóa tương ứng là `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Chọn đúng nhánh theo Spring Boot BOM của dự án; không trộn phiên bản Spring Security thủ công.

### 7.2. Cấu hình ClientRegistration

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

`openid` yêu cầu OIDC. `issuer-uri` giúp Spring Security khám phá metadata của OP khi provider hỗ trợ discovery và ràng buộc issuer. Thay URI và credentials bằng dữ liệu thật; không commit secret. Redirect URI công khai phải trùng cấu hình đăng ký của client ở OP.

### 7.3. SecurityFilterChain sử dụng repository

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

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

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)))
            .build();
    }
}
~~~

Ví dụ làm rõ điểm mở rộng repository; thực tế **không cần tự khai báo bean repository** nếu dùng mặc định. Quan trọng là Spring Security quản lý cùng request context ở cả authorization redirect và callback.

`oauth2Login()` hỗ trợ xác thực OAuth2/OIDC Servlet. Bạn không cần viết controller bắt `/login/oauth2/code/company` để tự parse `code` và `id_token`: callback đã được filter của Spring Security xử lý.

### 7.4. Spring Security lấy expected nonce từ đâu?

Trong quá trình OIDC Login, thành phần liên quan đến Authorization Code authentication sử dụng **authorization request được giữ lại** cùng dữ liệu ID Token của provider. Tùy phiên bản, nonce được tạo bởi default authorization request resolver/customizer cho OIDC và được giữ ở thuộc tính nội bộ của `OAuth2AuthorizationRequest`.

Luồng khái niệm:

~~~text
DefaultOAuth2AuthorizationRequestResolver
  -> xây authorization request
  -> state, OIDC nonce context, PKCE context khi áp dụng
  -> AuthorizationRequestRepository.save(...)

OAuth2LoginAuthenticationFilter
  -> nhận authorization code callback
  -> lấy authorization request đã lưu
  -> OAuth2/OIDC authentication provider
  -> nhận và xác minh ID Token
  -> nếu đã gửi nonce: đối chiếu ID Token nonce với request context
  -> Authentication thành công/thất bại
~~~

Các tên class/hành vi mặc định có thể khác ở một số phiên bản hoặc khi tùy biến; cần dựa vào contract của Spring Security đang dùng. **Ứng dụng không nên tự viết thêm một kiểm tra nonce qua controller sau khi login** để thay thế xác minh của authentication provider.

### 7.5. Đọc principal sau khi đã login

Một controller có thể lấy ID Token đã đi qua cơ chế OIDC login:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("idTokenHasNonceClaim",
            user.getIdToken().getClaims().containsKey("nonce"));
        return result;
    }
}
~~~

Trường boolean `idTokenHasNonceClaim` chỉ là dữ liệu quan sát **đã có claim hay không**, **không phải kết quả tự kiểm tra nonce**. Trong Code flow, thiếu nonce có thể phù hợp với một request không gửi nonce; muốn biết có ràng buộc nonce đúng hay không phải xem request/validator thực tế.

Không trả giá trị `user.getIdToken().getTokenValue()`, nonce, Access Token hay session cookie cho browser để debug.

## 8. Pseudocode: kiểm tra nonce nếu phải xây OIDC client riêng

Với Spring Security chuẩn, nên dùng validator sẵn có. Nếu một hệ thống đặc thù thực sự phải triển khai OIDC handler riêng, thứ tự kiểm tra cần bảo đảm:

~~~text
handleOidcCallback(callback, browserContext):
    pendingRequest = repository.consume(
        browserContext.session,
        callback.state
    )
    if pendingRequest == null:
        reject("authorization_request_not_found")

    if callback có OAuth authorization error:
        reject("authorization_denied_or_failed")

    tokenResponse = exchangeAuthorizationCode(
        callback.code,
        pendingRequest.redirectUri,
        pendingRequest.pkceVerifier,
        configuredClientAuthentication
    )

    idToken = tokenResponse.id_token
    if idToken == null:
        reject("missing_id_token")

    claims = verifyIdToken(
        idToken,
        trustedIssuer,
        expectedClientId,
        allowedSignatureAlgorithms,
        allowedJwks,
        currentTime
    )

    if pendingRequest.nonceWasSent:
        expected = deriveExactlyWhatWasSent(
            pendingRequest.savedNonceContext
        )
        if claims.nonce is missing or claims.nonce != expected:
            reject("nonce_validation_failed")

    // Các ràng buộc OIDC khác vẫn phải được xử lý.
    authenticate(issuer=claims.iss, subject=claims.sub)
~~~

Đây là **pseudocode giải thích thứ tự**, không phải implementation production. Một client OIDC đúng chuẩn còn phải xử lý nhiều điều kiện: issuer/audience/authorized party, algorithm và key restrictions, expiration/time claims, nonce, các trường hợp nhiều audience, response type, token hash claims khi cần, lỗi giao thức và lưu trữ trạng thái giao dịch.

Không lấy pseudocode trên thay bộ xác minh ID Token của thư viện trưởng thành.

### 8.1. Vì sao nonce phải so ở bước sau xác minh?

Kẻ tấn công có thể tạo một chuỗi có payload JSON gồm `nonce=expected-value` nếu ứng dụng chỉ decode chứ không xác minh chữ ký. Nonce **không biến JWT chưa được xác minh thành JWT đáng tin**. Client phải đảm bảo token thực sự do OP đáng tin phát hành và đúng audience, rồi mới sử dụng nonce để xác nhận ràng buộc giao dịch.

Trong cấu trúc xử lý thực tế, thư viện có thể thực hiện các bước xác minh với thứ tự nội bộ khác, nhưng không được **chấp nhận đăng nhập** trước khi toàn bộ điều kiện bắt buộc được thỏa mãn.

## 9. Thất bại nonce nên được xử lý thế nào?

Khi nonce không khớp, thiếu trong trường hợp request đã gửi nonce hoặc không thể khôi phục ngữ cảnh authorization request, ứng dụng phải **fail closed**: không tạo phiên đăng nhập mới dựa trên ID Token đó.

Trong Spring Security Servlet, lỗi thường kết thúc bằng `AuthenticationException` trong cơ chế OAuth2/OIDC login. Ứng dụng có thể cấu hình `AuthenticationFailureHandler` để điều hướng browser đến trang thân thiện.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuthFailureConfig {

    @Bean
    SecurityFilterChain oauthFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/auth/failed", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .failureHandler(new SimpleUrlAuthenticationFailureHandler(
                    "/auth/failed")))
            .build();
    }
}
~~~

Trang `/auth/failed` nên giải thích trung tính “Không thể hoàn tất đăng nhập; vui lòng thử lại”, tránh tiết lộ giá trị nonce/ID Token hoặc lỗi kỹ thuật nhạy cảm. **Không tự động redirect ngược về provider vô hạn**, vì tình huống mất session hoặc sai callback có thể lặp lại liên tục.

Lưu ý ví dụ này là **một SecurityFilterChain thay thế để minh họa xử lý lỗi**, không phải khối cấu hình cần đặt song song với chain ở phần trước. Khi kết hợp ứng dụng thật, cấu hình failure handler vào cùng chain đang xử lý OAuth2 callback.

### 9.1. Phân biệt lỗi nonce với các lỗi khác

| Dấu hiệu | Nguồn lỗi khả dĩ | Cách ứng xử |
| --- | --- | --- |
| Nonce claim sai expected nonce | ID Token không thuộc request đang xử lý hoặc provider/custom resolver không đồng bộ | Từ chối login, kiểm tra provider và request context |
| ID Token thiếu nonce trong khi request đã gửi nonce | Provider không phản ánh nonce hoặc converter/token sai | Từ chối login, sửa tích hợp |
| Authorization request không tìm thấy | Cookie/session mất, state mismatch, multi-node/multi-tab | Từ chối callback, sửa correlation/session |
| ID Token hết hạn | Thời gian/token lỗi | Từ chối token; kiểm tra clock và issuer |
| Chữ ký hoặc issuer không hợp lệ | Wrong JWKS, key rotation, tenant hoặc token không đáng tin | Từ chối, sửa trust configuration |
| `aud` không chứa client ID | ID Token được phát hành cho client khác | Từ chối, kiểm tra client registration |
| Token endpoint trả `invalid_grant` | Code đã dùng/hết hạn, PKCE/redirect mismatch | Điều tra token exchange; không kết luận nonce sai |
| Provider trả `error=access_denied` | User/admin không chấp thuận authorization | Xử lý consent failure; không có token thành công để kiểm tra nonce |

Một log hoặc exception có chữ “nonce” chỉ là gợi ý vị trí lỗi; không tắt kiểm tra nonce để “đăng nhập được” khi provider đang trả sai claim.

## 10. Những sai lầm phổ biến khi tùy biến Spring Security

### 10.1. Tự gắn nonce cố định vào mọi request

~~~java
// PHẢN VÍ DỤ — không dùng:
authorizationRequestBuilder.additionalParameters(
    params -> params.put("nonce", "fixed-nonce")
);
~~~

Nếu nonce lặp giữa các giao dịch, khả năng ràng buộc ID Token với lượt login riêng bị suy yếu. Nonce nên được sinh riêng bằng CSPRNG, không hard-code theo môi trường.

### 10.2. Sinh nonce lúc callback thay vì lúc authorization

Nonce được sinh sau khi nhận ID Token **không thể là giá trị đã gửi cho OP từ đầu**, nên không có tác dụng correlation. Giá trị mong đợi phải phát sinh từ request ban đầu và được lưu/có thể khôi phục.

### 10.3. Chỉ lưu state, làm mất nonce và PKCE

Một custom `AuthorizationRequestRepository` chỉ serialize `state` và `clientId` thường thiếu dữ liệu để Spring Security hoàn tất token exchange/nonce validation. Giữ nguyên thông tin cần thiết của `OAuth2AuthorizationRequest` và tiêu thụ đúng ngữ cảnh.

### 10.4. So sánh ID Token nonce với state

`state` và `nonce` có mục đích khác nhau. Một hệ thống gửi `state=ABC`, `nonce=XYZ` phải so ID Token nonce với `XYZ`, không phải `ABC`. Nếu request resolver đang băm nonce, so với biểu diễn chính xác đã gửi.

### 10.5. Bỏ qua nonce khi ID Token hợp lệ về chữ ký

Chữ ký đúng không chứng minh ID Token thuộc **request mới nhất**. Nếu nonce đã được yêu cầu, bỏ kiểm tra có thể mở đường cho token replay hoặc nhầm phiên giao dịch.

### 10.6. Bỏ qua chữ ký vì nonce đã khớp

Một chuỗi JSON có nonce bất kỳ có thể được tạo bởi attacker. Nếu ID Token chưa được xác minh, claim nonce **không đáng tin**. Hai nhóm kiểm tra là độc lập.

### 10.7. Đọc expected nonce từ request parameter bên ngoài

Callback OAuth2 thông thường không cần nhận một tham số `nonce` mới từ browser để xác minh ID Token. Nếu ứng dụng lấy `request.getParameter("nonce")` làm expected value, attacker có thể điều khiển dữ liệu đối chiếu. Phải dùng request context đã lưu ở phía client.

### 10.8. Lưu request vào biến singleton dùng chung

~~~java
// PHẢN VÍ DỤ — nguy hiểm khi có nhiều người dùng:
static OAuth2AuthorizationRequest lastRequest;
~~~

Hai người đăng nhập đồng thời có thể ghi đè state/nonce của nhau. Dùng repository ràng buộc theo session/browser; không dùng biến global chỉ giữ request cuối cùng.

### 10.9. Bật custom authorization request resolver nhưng không giữ logic mặc định

Nếu bạn thay toàn bộ `OAuth2AuthorizationRequestResolver`, hãy bảo đảm vẫn xử lý OIDC scope, state, PKCE, nonce, redirect URI và attributes cần thiết. Một resolver tự dựng không giữ nonce context có thể khiến validation thất bại; nguy hiểm hơn, sửa authentication provider để bỏ kiểm tra nhằm “sửa lỗi”.

Với nhu cầu thêm `prompt`, `login_hint` hoặc `acr_values`, ưu tiên cách mở rộng resolver có sẵn thay vì tự xây toàn bộ Authorization Code flow.

### 10.10. Hiển thị nonce/ID Token để hỗ trợ người dùng

Không gửi các giá trị này tới trang lỗi hoặc log browser. Khi cần điều tra, dùng correlation ID nội bộ và mã lỗi đã phân loại. Không ghi toàn bộ authorization URL có state, callback có code hay ID Token để dễ debug.

## 11. Trường hợp sử dụng với nhiều provider và nhiều registration

Một ứng dụng Servlet có thể đăng nhập bằng nhiều OIDC Provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee:
            provider: corp-oidc
            client-id: ${EMPLOYEE_CLIENT_ID}
            client-secret: ${EMPLOYEE_CLIENT_SECRET}
            scope: [openid, profile]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: [openid, email]
        provider:
          corp-oidc:
            issuer-uri: https://id.example.com/realms/company
          partner-oidc:
            issuer-uri: https://login.partner.example.net
~~~

Mỗi authorization request có:

- Registration/issuer tin cậy tương ứng.
- State riêng.
- Nonce riêng, nếu request dùng nonce.
- PKCE context riêng nếu bật.
- Redirect URI phù hợp đăng ký của client.

Nếu người dùng bắt đầu login với `employee` rồi callback trả token do `partner` phát hành, kiểm tra issuer/audience phải từ chối. Nếu token từ đúng issuer nhưng mang nonce thuộc request khác, kiểm tra nonce phải từ chối.

### 11.1. Hai tab đăng nhập song song

~~~text
Tab A: /oauth2/authorization/employee
  state=A-STATE
  nonce=A-NONCE

Tab B: /oauth2/authorization/partner
  state=B-STATE
  nonce=B-NONCE
~~~

Repository phải giữ đúng ngữ cảnh từng giao dịch. Với một số cách lưu chỉ có một pending request trên mỗi session, B có thể thay thế A, khiến callback A thất bại. Nếu cần đồng thời nhiều login, thiết kế repository theo state **và session binding**; mỗi callback chỉ dùng nonce của request tương ứng, không dùng nonce mới nhất của session.

Nếu callback A không còn request, **phải thất bại** và cho người dùng bắt đầu lại thay vì sử dụng nonce của B.

### 11.2. Reverse proxy và session phân tán

Một lần đăng nhập có thể đi qua nhiều instance Spring Boot. Nếu HTTP session không dùng chung, callback có thể không khôi phục request. Khi dùng Spring Session/Redis, cần bảo đảm dữ liệu request được serialize an toàn và có TTL phù hợp.

Kiểm tra cookie `Secure`, `HttpOnly`, `SameSite`, domain/path và địa chỉ callback công khai. Với Authorization Code callback top-level GET, `SameSite=Lax` thường phù hợp; nếu dùng POST response mode cross-site, cookie policy cần được thiết kế riêng. Không tự đổi thành `SameSite=None` nếu chưa đánh giá CSRF và cấu hình HTTPS.

## 12. Kiểm thử khả năng đối chiếu nonce

Kiểm thử cần phân biệt hai cấp độ:

1. **Test controller với mock `OidcUser`:** kiểm tra code ứng dụng sau khi người dùng đã được xác thực, nhưng **không tự chứng minh chữ ký/nonce validation** của giao thức.
2. **Integration test OIDC login thật hoặc test provider có thể điều khiển:** kiểm tra việc tạo authorization request, lưu context, nhận token, xác minh ID Token và xử lý nonce sai.

### 12.1. Những tình huống nên mô phỏng

| Kịch bản | Authorization request | ID Token trả về | Kết quả mong đợi |
| --- | --- | --- | --- |
| Nonce đúng | Gửi `nonce=N1` | Claim `nonce=N1` và token hợp lệ | Tiếp tục login nếu mọi kiểm tra khác đạt |
| Nonce sai | Gửi `nonce=N1` | Claim `nonce=N2` | Từ chối login |
| Thiếu nonce trong ID Token | Gửi `nonce=N1` | Không có claim nonce | Từ chối login |
| Code flow không gửi nonce | Không gửi nonce, đúng cấu hình/chuẩn áp dụng | Token không có nonce | Không tự coi đây là lỗi nonce; vẫn phải qua các kiểm tra OIDC khác |
| Token ký sai | Gửi `nonce=N1` | Nonce đúng nhưng signature sai | Từ chối login |
| Sai issuer | Gửi `nonce=N1` | Nonce đúng nhưng issuer khác | Từ chối login |
| Sai audience | Gửi `nonce=N1` | Nonce đúng nhưng `aud` khác client | Từ chối login |
| Session mất | Request ban đầu đã bị mất | Token có nonce tưởng như khớp | Không có ngữ cảnh tin cậy; từ chối |
| Nhiều tab | Hai request N1/N2 | Callback của A có N1 | Chỉ dùng request A; không lấy N2 |
| Callback phát lại | Request đã được tiêu thụ | Token cũ còn hạn | Không xác thực lại từ giao dịch đã hoàn tất |

### 12.2. Kiểm thử integration với provider giả lập

Một test OIDC có giá trị nên điều khiển được:

- Metadata discovery hoặc registration có issuer/JWKS tin cậy.
- Authorization endpoint trả code và state.
- Token endpoint trả ID Token có chữ ký test hợp lệ nhưng nonce được đặt thành **đúng, sai hoặc vắng mặt** tùy case.
- Session/browser context giữa chặng đi và callback.
- Kết quả SecurityContext, success/failure handler và HTTP response.

Test “nonce sai” phải làm cho **các điều kiện khác đều hợp lệ**, ví dụ signature, issuer, audience và expiration đúng, nếu muốn chứng minh chính nonce gây ra từ chối. Test ngược lại “nonce đúng nhưng chữ ký sai” bảo đảm ứng dụng không chỉ so nonce rồi coi là đủ.

Không nên giả lập đăng nhập bằng cách đặt thủ công `OidcUser` vào SecurityContext rồi kết luận validator nonce hoạt động; cách đó bỏ qua chính luồng cần kiểm tra.

### 12.3. Người dùng bấm “Back” hoặc đóng tab consent

Người dùng có thể rời màn hình provider, đóng tab hoặc quay về ứng dụng mà không có callback hợp lệ. Không bắt buộc failure handler được gọi vì **không có response từ OP**. Authorization request chờ sẽ hết hạn theo session/TTL; UI nên có đường bắt đầu lại và không tự cấp login.

## 13. Gỡ lỗi khi Spring Security báo nonce mismatch

Một bảng suy luận theo dấu hiệu:

| Triệu chứng | Khả năng cần xem | Hướng khắc phục |
| --- | --- | --- |
| ID Token có nonce nhưng validator báo sai | Provider echo khác nonce được gửi; client lưu khác biểu diễn; custom resolver băm/đổi nonce sai | Đối chiếu logic tạo/khôi phục nonce ở framework và contract provider, không log giá trị thật |
| Chỉ lỗi khi nhiều tab cùng login | Pending request bị ghi đè hoặc lấy nhầm state | Xem repository và khả năng lưu nhiều request theo state/session |
| Chỉ lỗi sau deploy nhiều node | Session không chia sẻ hoặc callback đến node khác | Kiểm tra distributed session/sticky routing và serialization |
| Đôi lúc không có nonce claim | Provider không echo tham số, request thực tế không gửi nonce, hoặc luồng khác nhau | Xem OIDC flow và cấu hình scope/authorization request |
| Callback báo authorization request not found | Cookie/session mất hoặc state mismatch | Kiểm tra `AuthorizationRequestRepository`, cookie, TTL, proxy |
| Token hợp lệ từ provider A nhưng login bằng registration B | Sai issuer/client/registration mapping | Kiểm tra issuer, audience, token endpoint và routing |
| Token expired/sai chữ ký cùng lúc | Lỗi ID Token validation trước hoặc song song với nonce | Sửa nguồn key, clock, issuer; không tắt validator |
| Có custom OAuth2 request resolver | Không giữ thuộc tính nội bộ nonce/PKCE | Dùng resolver của Spring làm nền, giữ nguyên request context |
| Callback bị xử lý hai lần | Pending request/code đã tiêu thụ | Tránh tự retry callback cũ; khởi tạo một transaction mới |

### 13.1. Thứ tự điều tra hợp lý

1. Xác định **registration ID** và issuer **được cấu hình tin cậy**, không lấy issuer từ token chưa xác minh rồi tự tin ngay.
2. Xác định request có thực sự là OIDC, có `scope=openid` và có gửi nonce không.
3. Xác định Spring Security có khôi phục được authorization request cho **state và session tương ứng** không.
4. Kiểm tra custom resolver/repository có bảo toàn nonce context và PKCE attributes không.
5. Kiểm tra provider trả ID Token đúng issuer/audience và có claim nonce theo request đã gửi hay không.
6. Xem có hai tab, callback lặp, session timeout, reverse proxy hoặc nhiều instance không.
7. Dựa trên lỗi cụ thể để sửa tích hợp; không tắt nonce/state/signature validation.

Chỉ ghi metadata đã phân loại vào log. Không chép ID Token, nonce, state, client secret, authorization code hoặc cookies vào ticket hỗ trợ công khai.

## 14. Ví dụ phân tích tình huống thực tế

### Tình huống A: ID Token đúng chữ ký, nonce từ giao dịch cũ

Request mới đã gửi nonce `N-NEW`, còn ID Token có nonce `N-OLD`, cùng issuer và audience, token chưa hết hạn.

**Kết luận:** không chấp nhận. Chữ ký và thời hạn không chứng minh token thuộc giao dịch mới; nonce đã gửi phải khớp.

### Tình huống B: OIDC provider không trả nonce trong Code flow dù client đã gửi

Client có authorization request với nonce `N-123`. Token endpoint trả ID Token không có claim nonce.

**Kết luận:** từ chối login trong giao dịch này. Kiểm tra cấu hình scope và nhà cung cấp; không sửa ứng dụng để bỏ yêu cầu xác minh đã được client kích hoạt.

### Tình huống C: Code flow không gửi nonce

Một cấu hình OIDC Authorization Code flow theo chuẩn không đặt tham số nonce. ID Token không chứa nonce nhưng được xác minh đầy đủ các điều kiện khác.

**Kết luận:** không tự coi thiếu nonce là lỗi nếu giao dịch thực sự không yêu cầu nonce và flow đó cho phép. Đây không phải lý do để bỏ những kiểm tra issuer, audience, signature, state hoặc PKCE.

### Tình huống D: Custom repository lưu state nhưng bỏ attributes

Sau khi callback, state khớp nhưng dữ liệu nonce/PKCE không còn nguyên. Token exchange có thể thiếu verifier hoặc nonce validation không thể thực hiện đúng.

**Kết luận:** sửa repository để lưu và phục hồi đúng `OAuth2AuthorizationRequest`, không tự so ID Token với state.

### Tình huống E: Hai người dùng dùng chung biến nonce toàn cục

User A bắt đầu login với `NA`, User B bắt đầu sau và ghi đè biến global bằng `NB`. Callback của A tới sau.

**Kết luận:** lỗi thiết kế concurrency và ranh giới phiên. Dùng state riêng từng request, lưu theo session/browser và không giữ expected nonce trong singleton field.

### Tình huống F: Session cookie không quay lại sau redirect

IdP trả callback và state đúng, nhưng browser đã mất cookie session nên server không tìm được original request.

**Kết luận:** không thể chấp nhận login chỉ dựa trên ID Token. Kiểm tra cookie Domain/Path/SameSite/Secure, reverse proxy, TTL và distributed session.

### Tình huống G: Nonce đúng nhưng audience sai

ID Token có nonce phù hợp, issuer tin cậy và chữ ký hợp lệ, nhưng `aud` là client ID của ứng dụng khác.

**Kết luận:** từ chối. Nonce không thay việc kiểm tra token được phát hành **cho client hiện tại**.

### Tình huống H: Người dùng từ chối cấp quyền

Provider trả `error=access_denied` ở authorization callback; chưa có token response thành công.

**Kết luận:** xử lý OAuth2/OIDC login failure và UX từ chối consent. Không thực hiện nonce validation trên một ID Token không tồn tại.

## 15. Tài liệu tham khảo

- OpenID Connect Core 1.0 — Authentication Request và ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Core 1.0 — Authorization Code Flow: https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth
- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — `AuthorizationRequestRepository` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html
- Spring Security — `OAuth2AuthorizationRequest` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html
- Proof Key for Code Exchange (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 16. Kết luận

Nonce trong OpenID Connect không chỉ là một chuỗi ngẫu nhiên xuất hiện trong ID Token. Giá trị ấy chỉ có ý nghĩa bảo mật khi **được tạo từ authorization request ban đầu, lưu đủ ngữ cảnh, gửi tới OP và được đối chiếu đúng lúc xác minh ID Token**.

~~~text
OIDC Client
  1. Sinh state + nonce + PKCE context (theo cấu hình/flow)
  2. Lưu OAuth2AuthorizationRequest trong repository
  3. Gửi authorization request có nonce tới OP
  4. Nhận callback code + state
  5. Khôi phục đúng request và kiểm tra correlation
  6. Đổi authorization code lấy ID Token
  7. Xác minh signature, iss, aud, exp, nonce nếu đã gửi...
  8. Chỉ chấp nhận Authentication khi tất cả điều kiện bắt buộc đạt

Nếu request ban đầu không có, nonce sai hoặc ID Token không hợp lệ:
  => Từ chối đăng nhập; không bypass bảo mật.
~~~

**Hãy để Spring Security thực hiện OIDC validation theo cơ chế chuẩn của framework**, trừ khi có yêu cầu tùy biến đã được thiết kế kỹ. Khi dùng custom authorization request resolver/repository, phải bảo toàn ràng buộc **state, nonce, PKCE, session và registration**. Nonce bổ sung bảo vệ chống nhầm/phát lại ID Token, nhưng chỉ có hiệu lực khi đi cùng các phép kiểm tra ID Token và Authorization Code flow đúng chuẩn.
