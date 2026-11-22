# 2.6. PKCE: code verifier, code challenge và phương thức S256

## 1. PKCE giải quyết vấn đề gì?

**Proof Key for Code Exchange (PKCE, đọc là “pixy”)** là phần mở rộng của OAuth 2.0 Authorization Code Flow, được định nghĩa trong RFC 7636. PKCE ràng buộc **authorization code** nhận qua đường chuyển hướng với một bí mật ngẫu nhiên do chính OAuth 2.0 Client tạo ra trước khi bắt đầu đăng nhập. Nhờ vậy, kẻ lấy được authorization code nhưng không có bí mật tương ứng sẽ không thể dùng code đó để đổi lấy token.

Trong một lần đăng nhập bằng OAuth 2.0/OIDC, ứng dụng (Client) đưa trình duyệt tới Authorization Server. Sau khi người dùng xác thực và đồng ý cấp quyền, Authorization Server trả một authorization code qua URL chuyển hướng. Đây là đoạn đi qua **front channel** (trình duyệt, hệ điều hành, redirect), nên có nguy cơ code bị lộ qua một ứng dụng bắt redirect, cấu hình redirect sai, extension độc hại hoặc thành phần trung gian bị xâm phạm.

Nếu chỉ biết authorization code đã đủ để đổi token, kẻ tấn công có thể tranh thủ dùng code trước Client hợp lệ. PKCE thêm một điều kiện:

- Lúc **gửi authorization request**, Client công bố một giá trị dẫn xuất gọi là **code challenge**.
- Lúc **đổi code lấy token**, Client phải trình ra **code verifier** bí mật đã dùng để tạo challenge.
- Authorization Server kiểm tra verifier có khớp challenge đã gắn với authorization code hay không. Không khớp thì từ chối cấp token.

PKCE ban đầu đặc biệt quan trọng với **public client** (mobile app, desktop app, SPA), vì các ứng dụng này không thể bảo mật lâu dài một <code>client_secret</code>. Ngày nay nên dùng PKCE với Authorization Code Flow cho cả **confidential client** như ứng dụng Spring Boot chạy phía server, nếu Authorization Server hỗ trợ. PKCE bổ sung lớp bảo vệ cho authorization code; nó không thay thế cơ chế xác thực Client dành cho confidential client.

> **Mấu chốt:** Kẻ tấn công có authorization code và biết code challenge vẫn không thể suy ngược code verifier đủ ngẫu nhiên từ challenge S256 để đổi token.

## 2. Ba thành phần cốt lõi

| Thành phần | Được tạo ở đâu? | Đi qua kênh nào? | Ý nghĩa |
|---|---|---|---|
| <code>code_verifier</code> | Client, cho **mỗi lần** bắt đầu Authorization Code Flow | Chỉ gửi trong yêu cầu tới **token endpoint** qua HTTPS | Chuỗi bí mật ngẫu nhiên để chứng minh quyền sở hữu lần yêu cầu ban đầu |
| <code>code_challenge</code> | Client, dẫn xuất từ verifier | Gửi đến **authorization endpoint** cùng yêu cầu xin code | Giá trị cam kết được Authorization Server lưu/liên kết với authorization code |
| <code>code_challenge_method</code> | Client chọn, thông thường <code>S256</code> | Gửi đến **authorization endpoint** | Cho server biết phép biến đổi từ verifier thành challenge |

### 2.1. Code verifier

Theo RFC 7636, <code>code_verifier</code> phải có độ dài **43–128 ký tự**, thuộc tập ký tự *unreserved*:

~~~text
A-Z a-z 0-9 - . _ ~
~~~

Verifier cần đủ entropy để không thể đoán được; cách tạo được khuyến nghị là lấy **32 byte ngẫu nhiên từ bộ sinh số ngẫu nhiên an toàn về mật mã (CSPRNG)**, rồi Base64URL-encode không padding. Ba mươi hai byte tương đương 256 bit dữ liệu ngẫu nhiên và thường cho chuỗi dài **43 ký tự**. Không dùng thời gian hiện tại, số tăng dần, UUID được tạo theo nguồn entropy yếu, tên người dùng, mật khẩu hay hằng số cấu hình làm verifier.

Verifier **khác nhau cho từng authorization request**. Nếu người dùng đăng nhập lại hoặc mở một lượt đăng nhập mới, Client phải tạo verifier mới.

### 2.2. Code challenge

Với phương thức S256, challenge được tính như sau:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Trong đó:

1. Biểu diễn verifier dưới dạng byte ASCII. Tập ký tự hợp lệ của verifier đều nằm trong ASCII.
2. Tính **SHA-256** của các byte này, nhận về **32 byte digest**.
3. Mã hóa digest bằng **Base64 URL-safe**, bỏ các ký tự padding <code>=</code>. Kết quả S256 thường dài **43 ký tự**.

SHA-256 là hàm băm, **không phải mã hóa có thể giải ngược**. Base64URL chỉ là cách biểu diễn byte an toàn trong tham số URL, không phải phép bảo mật. Tính bảo mật đến từ verifier ngẫu nhiên mạnh và việc chỉ tiết lộ challenge ở front channel.

Các lỗi tính toán phổ biến gồm băm chuỗi hex thay vì byte digest, dùng Base64 thông thường có <code>+</code>, <code>/</code> hoặc <code>=</code>, encode hai lần, và nhầm <code>SHA-256</code> với tên phương thức giao thức là <code>S256</code>.

### 2.3. Phương thức S256 và plain

RFC 7636 cũng định nghĩa <code>plain</code>, khi đó <code>code_challenge = code_verifier</code>. Cách này để lộ trực tiếp verifier trong authorization request và không bảo vệ được trước các kịch bản kẻ tấn công quan sát cả authorization request. Vì vậy, **ưu tiên S256**; không tự động chuyển xuống plain khi server báo lỗi. Nếu nhà cung cấp định danh không hỗ trợ S256, cần xem lại khả năng tương thích và cấu hình server.

## 3. Luồng Authorization Code + PKCE từ đầu đến cuối

Giả sử ứng dụng web Spring Boot là OAuth 2.0 Client, Authorization Server là hệ thống đăng nhập, và trình duyệt của người dùng được chuyển hướng giữa hai bên.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Security Client
    participant A as Authorization Server
    U->>B: Chọn đăng nhập
    B->>C: GET /oauth2/authorization/demo
    C->>C: Tạo verifier ngẫu nhiên, challenge = S256(verifier)
    C->>C: Lưu verifier gắn với authorization request/state
    C-->>B: 302 tới authorization endpoint
    B->>A: GET /authorize?code_challenge=...&code_challenge_method=S256
    A->>U: Xác thực, xin đồng ý (nếu cần)
    A->>A: Gắn challenge/method với authorization code
    A-->>B: 302 tới redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/demo?code=...&state=...
    C->>C: Kiểm tra state, tìm đúng verifier
    C->>A: POST /token kèm code và code_verifier
    A->>A: Tính S256(verifier), so khớp challenge đã lưu
    alt Verifier hợp lệ
        A-->>C: Access token (và ID token nếu là OIDC)
        C-->>B: Tạo phiên đăng nhập ứng dụng
    else Verifier không hợp lệ
        A-->>C: Lỗi token, thường invalid_grant
    end
~~~

Các bước cụ thể:

**Bước 1 — Tạo cặp verifier/challenge.** Client tạo verifier mới, tính challenge bằng S256, rồi giữ verifier an toàn cho đến khi đổi code. Với ứng dụng Spring Boot chạy trên server, trạng thái authorization request thường được giữ trong HTTP session phía server.

**Bước 2 — Gửi authorization request.** Trình duyệt chỉ nhận challenge và tên phương thức, không được nhận verifier qua URL:

~~~http
GET /authorize?response_type=code
    &client_id=demo-public-client
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
    &scope=openid%20profile
    &state=opaque-random-state
    &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
    &code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

Ví dụ HTTP trên được xuống dòng để dễ đọc; khi gửi thực tế, các tham số nằm trên một URL đã percent-encode hợp lệ. Giá trị challenge minh họa được lấy từ test vector của RFC 7636.

**Bước 3 — Authorization Server gắn PKCE vào code.** Server lưu challenge và method ứng với lần cấp authorization code đó; code còn liên kết với Client và redirect URI. Sau khi người dùng xác thực, server redirect trở lại Client với <code>code</code> và <code>state</code>.

**Bước 4 — Kiểm tra callback.** Client xác nhận <code>state</code> khớp lần khởi tạo, lấy lại verifier tương ứng rồi đổi code. Không lấy verifier từ query string do người dùng gửi vào callback.

**Bước 5 — Đổi code lấy token bằng back channel.** Với public client, yêu cầu điển hình là:

~~~http
POST /token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&
client_id=demo-public-client&
code_verifier=ORIGINAL_CODE_VERIFIER
~~~

Dấu xuống dòng của phần body ở đây chỉ để trình bày; request thực tế phải được form-encode hợp lệ. Token request phải dùng HTTPS. Với confidential client, còn có **xác thực Client** theo phương thức đã đăng ký (ví dụ HTTP Basic với client secret); PKCE vẫn thực hiện song song.

**Bước 6 — Server xác minh.** Với S256, server tính lại SHA-256/Base64URL từ verifier trong token request và so với challenge đã gắn với code. Nếu thiếu verifier, sai verifier hoặc server không tìm thấy thông tin PKCE phù hợp, token request bị từ chối. Authorization code thường ngắn hạn và chỉ được sử dụng một lần.

### Điều gì xảy ra nếu authorization code bị đánh cắp?

| Tình huống | Kẻ tấn công có gì? | Kết quả kỳ vọng |
|---|---|---|
| Code bị lộ qua redirect | Có <code>code</code>, biết <code>code_challenge</code>, **không** có verifier | Không đổi được token vì thiếu proof |
| Kẻ tấn công đoán verifier | Thấy challenge S256 | Không thực tế nếu verifier có 256 bit entropy và được tạo đúng |
| Kẻ tấn công chiếm luôn verifier hoặc session của Client | Có cả code lẫn verifier hợp lệ | PKCE không còn đủ; phải bảo vệ session, môi trường chạy và các kênh truyền |
| Client tái sử dụng verifier qua nhiều lần đăng nhập | Một verifier dùng cho nhiều code | Tăng phạm vi ảnh hưởng nếu verifier lộ; phải sinh mới mỗi lần |

## 4. Tự tạo và kiểm tra PKCE bằng Java

Trong ứng dụng Spring Security bình thường, framework có thể tạo và chuyển PKCE tự động. Đoạn Java sau giúp hiểu rõ thuật toán S256 và hữu ích khi kiểm tra khả năng tương tác với Authorization Server.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceUtil {
    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceUtil() {
    }

    public static PkcePair newPair() {
        byte[] randomBytes = new byte[32]; // 256 bit
        RANDOM.nextBytes(randomBytes);

        String verifier = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);

        return new PkcePair(verifier, toS256Challenge(verifier));
    }

    public static String toS256Challenge(String verifier) {
        if (verifier == null || !verifier.matches("[A-Za-z0-9._~-]{43,128}")) {
            throw new IllegalArgumentException("Invalid PKCE code_verifier");
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    public record PkcePair(String verifier, String challenge) {
    }
}
~~~

Các lựa chọn quan trọng trong ví dụ:

- <code>SecureRandom</code> cung cấp byte ngẫu nhiên phù hợp cho mục đích mật mã.
- <code>Base64.getUrlEncoder().withoutPadding()</code> tạo chuỗi URL-safe và loại dấu <code>=</code> ở cuối.
- <code>StandardCharsets.US_ASCII</code> tương ứng chính xác với biểu thức trong RFC 7636.
- Verifier luôn là **chuỗi gốc**, không phải digest; digest được Base64URL-encode mới là challenge.
- Không ghi verifier ra log và không tái sử dụng <code>PkcePair</code> giữa các lượt đăng nhập.

### 4.1. Test vector chuẩn của RFC 7636

RFC 7636 đưa ra ví dụ có thể dùng để kiểm tra hàm S256:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Ví dụ kiểm tra thủ công:

~~~java
String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String expected = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

if (!expected.equals(PkceUtil.toS256Challenge(verifier))) {
    throw new AssertionError("S256 result does not match RFC 7636");
}
~~~

Nếu kết quả khác test vector, hãy kiểm tra thứ tự **ASCII → SHA-256 byte digest → Base64URL không padding**. Không áp dụng thêm URL encoding trước khi tính hash.

## 5. PKCE trong Spring Security OAuth 2.0 Client

Spring Security OAuth2 Client có trách nhiệm dựng authorization request, lưu trạng thái request qua redirect, nhận callback và gửi token request. Khi cấu hình PKCE đúng, ứng dụng không cần tự giữ verifier trong controller hay tự dựng request <code>/token</code>.

### 5.1. Cấu hình tối thiểu cho OAuth2 Login/OIDC

Ví dụ dùng Spring Boot 3 và Spring Security 6, với một **public client** đã đăng ký ở Authorization Server:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: demo-public-client
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          demo:
            issuer-uri: https://idp.example.com
~~~

Đây là ví dụ cấu hình: thay <code>issuer-uri</code>, <code>client-id</code> và redirect URI theo nhà cung cấp thật; Authorization Server phải có metadata OIDC discovery hợp lệ tại issuer đã cấu hình. Tại server, đăng ký chính xác redirect URI tương ứng với ứng dụng. <code>openid</code> trong scope cho biết đây là luồng OIDC; nếu chỉ cần OAuth 2.0 thì scope phụ thuộc API và không nhất thiết có <code>openid</code>.

Với cấu hình security cơ bản:

~~~java
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
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Người dùng bắt đầu luồng tại đường dẫn mặc định:

~~~text
GET /oauth2/authorization/demo
~~~

Trong các phiên bản Spring Security hiện đại có hỗ trợ PKCE, <code>DefaultOAuth2AuthorizationRequestResolver</code> sẽ tự áp dụng PKCE khi Client là public client với <code>client-authentication-method: none</code> và Authorization Code Flow. Khi callback trở lại <code>/login/oauth2/code/demo</code>, Spring Security tìm authorization request đã lưu, sử dụng verifier để đổi token rồi thiết lập authentication cho ứng dụng.

**Không suy ra việc PKCE hoạt động chỉ vì ứng dụng đăng nhập thành công.** Khi tích hợp một phiên bản/framework cụ thể, hãy kiểm tra authorization request thực tế có đủ <code>code_challenge</code> và <code>code_challenge_method=S256</code>, đồng thời token request có verifier. Không log giá trị bí mật khi kiểm tra.

### 5.2. Ép áp dụng PKCE bằng authorization request customizer

Với **confidential client** (có client secret) hoặc khi muốn chủ động yêu cầu PKCE, có thể cấu hình <code>OAuth2AuthorizationRequestCustomizers.withPkce()</code> trên resolver:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

Đây là **cấu hình thay thế** cho <code>SecurityConfig</code> ở mục 5.1, không định nghĩa đồng thời hai bean filter chain giống nhau. Tùy phiên bản Spring Security, điểm mở rộng API có thể khác; ví dụ này sử dụng API trong Spring Security 6.

Customizer thực hiện hai phần phải đi cùng nhau: thêm <code>code_challenge</code> và <code>code_challenge_method</code> vào authorization request gửi tới Authorization Server, đồng thời giữ <code>code_verifier</code> trong thuộc tính của authorization request nội bộ để token exchange sử dụng sau callback. **Chỉ tự thêm challenge vào URL** mà không lưu verifier sẽ khiến bước đổi token thất bại.

Với confidential client, vẫn cấu hình phương thức xác thực Client như <code>client_secret_basic</code> hoặc cơ chế khác do Authorization Server yêu cầu. Không đưa client secret vào JavaScript hay URL. Cấu hình bí mật qua secret store/biến môi trường phù hợp với hạ tầng.

### 5.3. Vì sao lưu authorization request quan trọng?

Authorization request và token request cách nhau một lượt đi qua trình duyệt. Trong khoảng đó Client phải nhớ verifier của **đúng** request khởi tạo. Spring Security dùng <code>AuthorizationRequestRepository</code> để giữ trạng thái này; cách mặc định cho OAuth2 Login là <code>HttpSessionOAuth2AuthorizationRequestRepository</code>.

Khi dùng repository tùy biến (ví dụ lưu bằng cookie hoặc Redis), cần bảo toàn các thành phần mà Spring Security sử dụng để hoàn thành flow, bao gồm <code>state</code> và **thuộc tính chứa verifier** của <code>OAuth2AuthorizationRequest</code>. Chỉ giữ <code>redirectUri</code>, <code>state</code> và các additional parameters thường không đủ. Nếu verifier bị mất hoặc bị ghi đè giữa các lượt đăng nhập, Authorization Server có thể trả <code>invalid_grant</code>.

Với nhiều cửa sổ đăng nhập song song, cần phân biệt các authorization request theo <code>state</code> hoặc cơ chế tương đương, tránh lấy verifier của cửa sổ A để đổi code từ cửa sổ B. Không tự lưu verifier lâu dài ở database nếu chỉ cần lưu tạm trong phiên đăng nhập; xóa trạng thái dùng một lần khi kết thúc.

## 6. Phân biệt PKCE với state, nonce và client secret

PKCE thường xuất hiện cùng nhiều cơ chế bảo vệ khác trong OAuth 2.0/OIDC, nhưng chúng có vai trò khác nhau.

| Cơ chế | Điểm kiểm tra | Mục đích chính |
|---|---|---|
| <code>state</code> | Client kiểm tra khi nhận authorization response | Liên kết callback với yêu cầu ban đầu, phòng chống nhầm lẫn phiên và CSRF trong luồng đăng nhập |
| **PKCE** (<code>code_verifier</code>/<code>code_challenge</code>) | Authorization Server kiểm tra tại token endpoint | Chỉ Client giữ verifier mới có thể đổi authorization code đã cấp |
| <code>nonce</code> của OIDC | OIDC Client kiểm tra trong ID token | Liên kết ID token với yêu cầu xác thực, hạn chế phát lại/chèn token |
| <code>client_secret</code> hoặc private-key client authentication | Authorization Server xác thực Client tại token endpoint | Chứng minh danh tính một **confidential client** |
| HTTPS/TLS | Khi truyền yêu cầu, callback và token | Chống nghe lén/chỉnh sửa dữ liệu trên đường truyền |

Một lượt OIDC Authorization Code Flow có thể đồng thời có <code>state</code>, <code>nonce</code>, PKCE và client authentication. Không dùng PKCE để thay hoàn toàn <code>state</code>, và không nhầm OIDC <code>nonce</code> với PKCE verifier. PKCE cũng không bảo đảm access token được dùng đúng mục đích sau khi cấp; token vẫn cần bảo vệ theo chính sách ứng dụng.

## 7. Các lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Authorization request không có <code>code_challenge</code> | Chưa bật PKCE; cấu hình Client không được nhận diện là public; custom resolver bỏ qua customizer | Xem cấu hình registration/resolver và yêu cầu đầu ra của authorization endpoint |
| <code>code_challenge_method=plain</code> hoặc method bị thiếu | Client/server cấu hình không khớp; tự dựng request sai | Dùng <code>S256</code>, xác nhận Authorization Server hỗ trợ và bắt buộc phương thức này |
| Token endpoint trả <code>invalid_grant</code> | Verifier sai/mất, code hết hạn/đã dùng, sai redirect URI hoặc sai Client | Kiểm tra tương quan <code>state</code>, lưu trữ authorization request, code dùng một lần và URI khớp |
| Token endpoint trả <code>invalid_client</code> | Client authentication bị từ chối | Kiểm tra đăng ký public/confidential và phương thức xác thực Client; không quy kết ngay cho PKCE |
| Lỗi khi chạy nhiều tab đăng nhập | Verifier hoặc authorization request của lượt trước bị ghi đè | Lưu các request độc lập và tra lại theo state |
| S256 tính ra khác test vector | Hash nhầm đầu vào, Base64 không URL-safe, padding hoặc encode thêm | Dùng byte ASCII, SHA-256 và Base64URL không padding đúng thứ tự |
| PKCE hoạt động cục bộ nhưng lỗi sau reverse proxy | URL callback/base URL khác URI đã đăng ký, session/cookie không được giữ | Kiểm tra cấu hình forwarded headers, redirect URI, session affinity hoặc kho session chia sẻ |
| Login thất bại sau khi tùy biến <code>AuthorizationRequestRepository</code> | Repository làm mất thuộc tính chứa verifier | Bảo toàn đầy đủ authorization request mà bộ xử lý token cần |

### Kiểm tra luồng mà không làm lộ verifier

Khi phân tích lỗi trong môi trường phát triển:

1. Xác nhận authorization request có <code>response_type=code</code>, <code>code_challenge</code> và <code>code_challenge_method=S256</code>.
2. Xác nhận yêu cầu đến token endpoint có **tham số** <code>code_verifier</code>, nhưng không ghi giá trị ra log, APM, metrics hay ảnh chụp màn hình.
3. Xác nhận token request thuộc đúng authorization request, thông qua state/session và redirect URI.
4. Kiểm tra client registration tại Authorization Server có yêu cầu/cho phép PKCE S256 và phương thức client authentication đúng loại ứng dụng.
5. Kiểm tra code chưa bị dùng trước đó và thời gian tồn tại của session, cookie, authorization request.

Không tắt PKCE, chuyển xuống plain, bỏ kiểm tra state hoặc chấp nhận redirect URI tùy ý chỉ để vượt qua lỗi tích hợp.

## 8. Thiết kế an toàn khi triển khai thực tế

**Tạo ngẫu nhiên đúng cách.** Mỗi lần khởi tạo flow tạo verifier độc lập từ CSPRNG; 32 byte ngẫu nhiên Base64URL không padding là lựa chọn dễ triển khai đúng. Không tái sử dụng verifier cố định theo tài khoản, thiết bị hoặc phiên đăng nhập.

**Giữ verifier ngoài front channel.** Chỉ challenge đi qua authorization URL. Verifier không nên xuất hiện trong URL, query parameter của callback, local log, analytics hay error page. Với server-side Spring Boot Client, giữ verifier trong authorization request được lưu an toàn ở server, thông qua session hoặc kho lưu trữ tương ứng.

**Dùng S256 và HTTPS.** Cả authorization endpoint, callback triển khai thực tế và token endpoint phải được cấu hình HTTPS phù hợp. Nếu nhà cung cấp không hỗ trợ S256, xử lý như vấn đề tương thích/bảo mật thay vì âm thầm bỏ PKCE.

**Ràng buộc và dọn trạng thái.** State và verifier phải gắn với cùng một authorization attempt. Khi thành công, thất bại, hết hạn hoặc hủy yêu cầu, loại bỏ trạng thái tạm theo chính sách của ứng dụng. Authorization code là giá trị một lần và không nên thử dùng lại.

**Không bỏ các kiểm soát khác.** PKCE chống việc sử dụng code bị chặn mà thiếu verifier; nó không xử lý XSS, chiếm session, đánh cắp access token/refresh token, cấu hình redirect URI quá rộng hoặc Authorization Server bị xâm nhập. Với OIDC, Client vẫn phải kiểm tra ID token đúng issuer, audience, thời gian hiệu lực và các điều kiện tương ứng theo thư viện.

## 9. Câu hỏi tình huống và bài thực hành

**Tình huống A.** Một mobile app gửi <code>code_challenge_method=S256</code>, nhưng trong token request lại gửi challenge làm <code>code_verifier</code>. Server có cấp token không?

**Đáp án:** Không. Server sẽ tính S256 của chuỗi được gửi làm verifier và nhận kết quả không bằng challenge đã lưu. Token request phải chứa **verifier ban đầu**, không phải challenge.

**Tình huống B.** Ứng dụng Spring Boot có <code>client_secret</code> nên nhóm phát triển muốn bỏ PKCE. Làm vậy có hợp lý không?

**Đáp án:** Client secret xác thực ứng dụng phía server; PKCE ràng buộc authorization code với lần khởi tạo flow. Hai cơ chế giải quyết các rủi ro khác nhau. Nên tiếp tục sử dụng S256 khi Authorization Server hỗ trợ.

**Tình huống C.** Lượt đăng nhập ở tab A tạo verifier A; tab B tạo verifier B. Callback của tab A dùng verifier B. Điều gì xảy ra?

**Đáp án:** Challenge gắn với code của tab A được tính từ verifier A. Dùng verifier B dẫn tới không khớp và token request bị từ chối. Cần tra đúng authorization request theo state và duy trì trạng thái riêng giữa các lượt.

**Thực hành đề xuất:** Tạo một cặp PKCE bằng <code>PkceUtil.newPair()</code> rồi xác nhận verifier dài 43 ký tự và chỉ chứa tập ký tự hợp lệ. Dùng test vector RFC 7636 để xác nhận hàm <code>toS256Challenge</code>. Trong ứng dụng Spring Security OAuth2 Login dùng một Authorization Server hỗ trợ PKCE, quan sát authorization request chứa challenge S256, hoàn thành login và xác nhận cơ chế đổi token dùng verifier mà không đưa verifier ra URL trình duyệt. Cuối cùng, thử làm mất trạng thái authorization request trong môi trường thử nghiệm để quan sát tại sao token exchange thất bại.

## 10. Ghi nhớ kiến thức

- PKCE mở rộng **Authorization Code Flow** bằng một bí mật ngẫu nhiên dùng một lần ở phía Client.
- **Verifier** được giữ kín cho đến token request; **challenge** được đưa vào authorization request.
- **S256 = Base64URL(SHA-256(ASCII(verifier)))**, không padding. Tên phương thức truyền trên giao thức là <code>S256</code>.
- Trong Spring Security, cấu hình OAuth2 Client phù hợp và sử dụng authorization request resolver/customizer để framework giữ verifier và gửi lại khi đổi code.
- PKCE bảo vệ authorization code; <code>state</code>, OIDC <code>nonce</code>, client authentication, HTTPS và an toàn phiên vẫn có nhiệm vụ riêng.

### Tài liệu chuẩn để tra cứu thêm

- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients:** định nghĩa verifier, challenge, S256, test vector và trình tự xác minh.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** nền tảng Authorization Code Grant và token endpoint.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ luồng OAuth 2.0 hiện đại, bao gồm sử dụng PKCE.
- **Spring Security Reference — OAuth2 Client / OAuth2 Login:** cấu hình ClientRegistration, authorization request resolver, PKCE customizer và tích hợp Authorization Code Flow.
