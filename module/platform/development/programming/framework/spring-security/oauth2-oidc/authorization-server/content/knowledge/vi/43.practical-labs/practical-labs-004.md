# Xây dựng client public dùng PKCE và client dịch vụ dùng Client Credentials

Trong một hệ thống OAuth 2.0, ứng dụng chạy trong trình duyệt và dịch vụ chạy ở backend có khả năng giữ bí mật khác nhau. Ứng dụng trình duyệt là **public client**: người dùng có thể xem mã JavaScript và mọi cấu hình được gửi xuống trình duyệt, vì vậy không thể bảo vệ một client secret lâu dài. Dịch vụ backend là **confidential client**: nó có thể giữ secret trong kho bí mật của máy chủ và xác thực với Authorization Server.

Bài thực hành này xây dựng cả hai loại client với Spring Authorization Server. Public client dùng Authorization Code grant kết hợp Proof Key for Code Exchange (PKCE) để đăng nhập và xin scope cho người dùng. Client dịch vụ dùng Client Credentials grant để lấy access token cho các lời gọi giữa hai backend. Hai client được đăng ký riêng, chỉ có grant type và scope cần thiết.

Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, nơi ta thiết kế và vận hành Authorization Server từ quản lý client, consent, cấp token, PKCE, refresh token đến bảo vệ endpoint, ký khóa và kiểm thử luồng bảo mật. Chương **Thực hành tổng hợp** kết hợp các thành phần đó thành một luồng có thể chạy và kiểm tra được.

## 1. Kết quả cần đạt và sơ đồ lab

Khi hoàn thành, ta có thể:

- Đăng ký một public client không có client secret, bắt buộc PKCE với phương thức S256.
- Hoàn tất Authorization Code flow, kiểm tra state ở callback và đổi code bằng đúng code verifier.
- Đăng ký một confidential client với client authentication bằng client secret qua HTTP Basic.
- Cấp access token bằng Client Credentials và gọi một resource endpoint được bảo vệ.
- Xác minh scope, redirect URI và các trường hợp request không hợp lệ.

Lab dùng ba tiến trình local:

| Thành phần | Địa chỉ | Vai trò |
|---|---|---|
| Spring Authorization Server | http://127.0.0.1:9000 | Đăng nhập, consent, authorization endpoint và token endpoint |
| Ứng dụng public client | http://127.0.0.1:8081 | Chạy trong trình duyệt, nhận authorization code tại callback |
| Resource Server | http://127.0.0.1:8082 | Cung cấp API đơn hàng được bảo vệ bằng access token |

Đây là địa chỉ dành cho máy phát triển. Khi triển khai thật, dùng HTTPS, hostname đã đăng ký và redirect URI chính xác. Authorization Server cần có user authentication, consent page, security filter chain và signing key hoạt động trước khi chạy lab. Issuer phải nhất quán giữa metadata, JWT và cấu hình Resource Server.

## 2. Đăng ký hai client trong Spring Authorization Server

Tạo hai RegisteredClient với cấu hình tối thiểu. Public client chỉ dùng Authorization Code, không có secret và bắt buộc PKCE. Service client chỉ dùng Client Credentials, xác thực bằng client secret qua HTTP Basic:

~~~java
@Configuration
public class LabClientConfiguration {

    @Bean
    PasswordEncoder clientPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder clientPasswordEncoder) {

        RegisteredClient browserClient = RegisteredClient
                .withId("browser-public-client-id")
                .clientId("browser-public-client")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("http://127.0.0.1:8081/callback")
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        RegisteredClient serviceClient = RegisteredClient
                .withId("orders-service-client-id")
                .clientId("orders-service")
                .clientSecret(clientPasswordEncoder.encode("local-service-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("orders.read")
                .scope("orders.write")
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(browserClient, serviceClient);
    }
}
~~~

Các kiểu trong ví dụ thuộc những package Spring Security OAuth2 Authorization Server, Spring Security Crypto và Java Time. Hãy bổ sung import tương ứng cho phiên bản Spring Authorization Server đang dùng. Nếu ứng dụng đã có bean PasswordEncoder, dùng bean hiện tại thay vì khai báo bean thứ hai.

Public client dùng ClientAuthenticationMethod.NONE. Giá trị này có nghĩa là client không xác thực bằng secret tại token endpoint; PKCE bảo vệ việc đổi authorization code bằng cách ràng buộc code với một verifier chỉ client khởi tạo giữ. Public client vẫn phải gửi client_id để server xác định đăng ký client. Redirect URI phải khớp chính xác với URI đã đăng ký.

Service client dùng ClientAuthenticationMethod.CLIENT_SECRET_BASIC. Secret được mã hóa bằng PasswordEncoder trước khi lưu vào RegisteredClient. Giá trị secret trong ví dụ chỉ dùng ở local lab; môi trường thật phải lấy secret từ secret manager hoặc biến môi trường được bảo vệ.

Ví dụ dùng InMemoryRegisteredClientRepository để dựng lab nhanh. Khi chạy nhiều instance hoặc cần giữ client sau khi khởi động lại, thay bằng JdbcRegisteredClientRepository và datasource riêng. Không để cả repository production và repository in-memory cùng đăng ký hai bean không rõ thứ tự trong một context.

Authorization Server cũng cần cấu hình issuer phù hợp với địa chỉ lab:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("http://127.0.0.1:9000")
            .build();
}
~~~

Đảm bảo signing key/JWKSource đã được cấu hình để ký JWT access token và JWKS endpoint chỉ công bố public key. Cấu hình endpoint, filter chain và trang đăng nhập của Authorization Server cần được bật theo cấu trúc ứng dụng. Public client sẽ được chuyển đến trang đăng nhập khi người dùng chưa có phiên xác thực; consent được hiển thị nếu client yêu cầu consent.

## 3. Chạy Authorization Code với PKCE cho public client

PKCE tạo một cặp giá trị cho mỗi lần authorization:

- **code_verifier** là chuỗi ngẫu nhiên do public client tạo và giữ lại đến khi đổi code.
- **code_challenge** là phép biến đổi SHA-256 của verifier, được gửi trong authorization request.

Với phương thức S256, Authorization Server lưu challenge cùng authorization code. Khi client đổi code, server tính lại challenge từ verifier được gửi lên và so sánh. Người chỉ lấy được authorization code sẽ không thể đổi code nếu không có verifier tương ứng.

Trong trang public client, tạo verifier, challenge và state bằng Web Crypto API. Ví dụ sau có thể chạy trong ứng dụng trình duyệt được phục vụ trên localhost:

~~~javascript
const randomHex = (size = 32) =>
  Array.from(crypto.getRandomValues(new Uint8Array(size)),
    value => value.toString(16).padStart(2, "0")).join("");

const codeVerifier = randomHex(32);
const state = randomHex(16);

const digest = await crypto.subtle.digest(
  "SHA-256",
  new TextEncoder().encode(codeVerifier)
);

const codeChallenge = btoa(
  String.fromCharCode(...new Uint8Array(digest))
)
  .replaceAll("+", "-")
  .replaceAll("/", "_")
  .replaceAll("=", "");

sessionStorage.setItem("pkce_verifier", codeVerifier);
sessionStorage.setItem("oauth_state", state);

const authorizationUrl = new URL(
  "http://127.0.0.1:9000/oauth2/authorize"
);
authorizationUrl.search = new URLSearchParams({
  response_type: "code",
  client_id: "browser-public-client",
  redirect_uri: "http://127.0.0.1:8081/callback",
  scope: "orders.read",
  state,
  code_challenge: codeChallenge,
  code_challenge_method: "S256"
}).toString();

window.location.assign(authorizationUrl);
~~~

Mỗi lần bắt đầu authorization flow, tạo verifier và state mới. Lưu verifier cùng state trong session của tab để dùng tại callback. Không ghi verifier vào log, URL, analytics hoặc nơi có thể bị gửi đến bên thứ ba. Dùng HTTPS trong production; Web Crypto API cần secure context, và localhost được trình duyệt xem là secure context cho phát triển.

Authorization Server sẽ yêu cầu người dùng đăng nhập nếu chưa có session. Sau khi người dùng chấp thuận scope orders.read, server chuyển trình duyệt về callback với authorization code và state. Callback phải kiểm tra state trước khi đổi code:

~~~javascript
const callbackUrl = new URL(window.location.href);
const authorizationCode = callbackUrl.searchParams.get("code");
const returnedState = callbackUrl.searchParams.get("state");
const expectedState = sessionStorage.getItem("oauth_state");
const codeVerifier = sessionStorage.getItem("pkce_verifier");

if (!authorizationCode || !returnedState || returnedState !== expectedState) {
  throw new Error("Authorization response state is invalid");
}

if (!codeVerifier) {
  throw new Error("PKCE verifier is missing");
}

const tokenResponse = await fetch(
  "http://127.0.0.1:9000/oauth2/token",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: "browser-public-client",
      code: authorizationCode,
      redirect_uri: "http://127.0.0.1:8081/callback",
      code_verifier: codeVerifier
    })
  }
);

const tokenResult = await tokenResponse.json();
if (!tokenResponse.ok) {
  throw new Error(tokenResult.error || "Token exchange failed");
}

sessionStorage.removeItem("pkce_verifier");
sessionStorage.removeItem("oauth_state");
// Giữ access token trong bộ nhớ của ứng dụng và sử dụng theo scope đã cấp.
~~~

Public client không gửi Authorization header chứa client secret. Request gửi client_id để nhận diện client, authorization code, redirect URI và code verifier. Redirect URI khi đổi code phải giống URI đã gửi trong authorization request và URI được đăng ký. Authorization code chỉ được sử dụng một lần và có thời hạn ngắn.

Vì browser gọi token endpoint ở origin khác, cấu hình CORS của Authorization Server cần allowlist chính xác origin của public client, ví dụ http://127.0.0.1:8081, và cho phép các phương thức/header cần thiết. CORS chỉ cho phép trình duyệt thực hiện request; PKCE và state mới bảo vệ authorization flow. Không dùng CORS thay cho PKCE. Không cho phép wildcard origin cùng credentials trong cấu hình thật.

Sau khi có access token, public client có thể gọi API với scope orders.read:

~~~javascript
const apiResponse = await fetch(
  "http://127.0.0.1:8082/api/orders",
  {
    headers: {
      Authorization: "Bearer " + tokenResult.access_token
    }
  }
);
~~~

Resource Server phải xác minh chữ ký, issuer, thời hạn và scope của JWT. Với Spring Resource Server, có thể cấu hình issuer URI trùng với Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://127.0.0.1:9000
~~~

Ví dụ endpoint chỉ cho phép scope orders.read:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    List<String> listOrders() {
        return List.of("order-1001", "order-1002");
    }
}
~~~

Ứng dụng Resource Server cần bật method security nếu dùng @PreAuthorize. Có thể thay bằng authorization rule trong SecurityFilterChain nếu dự án đang quản lý quyền ở tầng HTTP.

## 4. Lấy access token cho client dịch vụ bằng Client Credentials

Service client chạy ở backend, vì vậy có thể giữ client secret. Với cấu hình đã đăng ký, client gửi POST đến token endpoint, xác thực bằng HTTP Basic và yêu cầu scope orders.read:

~~~bash
curl --user "orders-service:local-service-secret" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders.read" \
  http://127.0.0.1:9000/oauth2/token
~~~

Response thành công có dạng:

~~~json
{
  "access_token": "<signed-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Giá trị token trong ví dụ đã được thay bằng placeholder. Client Credentials không cần trình duyệt, redirect URI, authorization code, state, PKCE hoặc consent của người dùng. Client xác thực danh tính ứng dụng bằng client secret và chỉ nhận quyền đã đăng ký.

Dùng access token gọi Resource Server:

~~~bash
curl --header "Authorization: Bearer <ACCESS_TOKEN>" \
  http://127.0.0.1:8082/api/orders
~~~

Để tích hợp service client trong ứng dụng Spring, có thể dùng OAuth2 Client support để tự lấy và quản lý access token. Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-service:
            provider: local-authorization-server
            client-id: orders-service
            client-secret: ${ORDERS_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - orders.read
        provider:
          local-authorization-server:
            token-uri: http://127.0.0.1:9000/oauth2/token
~~~

Biến ORDERS_SERVICE_CLIENT_SECRET phải được cấp từ môi trường chạy service hoặc secret manager. Không đóng gói secret vào frontend bundle, mobile app, repository hoặc image dùng chung.

Có thể tạo OAuth2AuthorizedClientManager để service lấy token theo registration:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClientService) {

    OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Khi cần gọi API, tạo OAuth2AuthorizeRequest với registration ID orders-service và một principal đại diện cho service. Manager sẽ lấy access token hoặc yêu cầu token mới khi token hiện tại không còn hợp lệ theo chính sách. Với Client Credentials, ứng dụng lấy token mới bằng client authentication; không dùng refresh token.

## 5. Xác minh hai luồng hoạt động

Thực hiện theo thứ tự sau để xác định lỗi nằm ở đăng ký client, authorization flow hay resource server:

1. Khởi động Authorization Server tại cổng 9000 và xác minh issuer/metadata cùng JWKS endpoint hoạt động.
2. Khởi động Resource Server tại cổng 8082 và xác minh API yêu cầu bearer token.
3. Chạy public client tại cổng 8081. Tạo PKCE verifier/challenge, chuyển trình duyệt đến authorization endpoint, đăng nhập và chấp thuận orders.read.
4. Tại callback, xác minh state rồi đổi authorization code bằng code verifier. Kiểm tra response có access token và scope orders.read.
5. Gọi GET /api/orders bằng access token vừa nhận. Resource Server phải xác minh JWT và cho phép scope tương ứng.
6. Gửi Client Credentials request bằng orders-service. Xác minh token endpoint trả access token có scope orders.read.
7. Dùng access token của service client gọi API. Thử yêu cầu orders.write nếu API có endpoint tương ứng để xác minh quyền được giới hạn theo scope.

Nếu Resource Server không chấp nhận token, kiểm tra issuer, signing key/JWKS, thời gian hệ thống, audience (nếu ứng dụng yêu cầu audience riêng) và mapping scope thành authority. Nếu token được ký bằng key mới nhưng Resource Server còn cache JWKS cũ, kiểm tra khả năng refresh JWKS và thời gian cache.

## 6. Kiểm thử các trường hợp bị từ chối

| Client/luồng | Thao tác | Kết quả cần xác minh |
|---|---|---|
| Public client | Bỏ code_challenge | Authorization request bị từ chối vì client bắt buộc PKCE |
| Public client | Dùng code_verifier sai | Token endpoint từ chối đổi code, thường là invalid_grant |
| Public client | Gửi redirect_uri khác URI đã đăng ký | Authorization hoặc token request bị từ chối |
| Public client | Callback nhận state không khớp | Client dừng xử lý trước khi đổi code |
| Public client | Dùng lại authorization code | Token endpoint từ chối code đã tiêu thụ |
| Service client | Gửi client secret sai | Client authentication thất bại, lỗi invalid_client |
| Service client | Yêu cầu scope chưa đăng ký | Token endpoint từ chối scope, thường là invalid_scope |
| Service client | Gọi API yêu cầu scope không có trong token | Resource Server trả 403 |
| Cả hai | Gửi token hết hạn hoặc chữ ký sai | Resource Server từ chối bearer token |

Khi kiểm tra PKCE, xác minh server chỉ chấp nhận phương thức S256 theo chính sách client. Không chỉ kiểm tra trường code_challenge có mặt; cần chứng minh verifier đúng được chấp nhận và verifier sai bị từ chối. Với state, trách nhiệm so sánh giá trị callback thuộc client; Authorization Server không thay thế bước kiểm tra này.

## 7. Sự khác nhau khi vận hành hai client

Public client không có secret để bảo vệ, do đó cần PKCE, state, redirect URI chính xác, access token lifetime ngắn và lưu token an toàn trong trình duyệt. Tránh lưu access token dài hạn trong localStorage nếu mô hình ứng dụng có nguy cơ bị đọc bởi script cùng origin. Bảo vệ ứng dụng trước XSS và chỉ gửi token qua HTTPS.

Service client phải giữ secret ở backend. Dùng secret riêng cho từng service, xoay vòng khi cần và giới hạn scope theo nhiệm vụ. Không đưa secret vào log hoặc exception message. Nếu hệ thống hỗ trợ phương thức xác thực client mạnh hơn như private_key_jwt hoặc mutual TLS, có thể áp dụng cho môi trường yêu cầu assurance cao hơn.

Không dùng Client Credentials để đại diện cho hành động của một người dùng. Nếu nghiệp vụ cần quyền và danh tính người dùng, dùng Authorization Code flow hoặc cơ chế delegation phù hợp. Ngược lại, không buộc service-to-service phải mở trang đăng nhập người dùng khi chỉ cần danh tính ứng dụng.

## 8. Checklist hoàn tất lab

- Public client có client authentication method NONE và không chứa client secret.
- Public client chỉ được cấp Authorization Code grant và bắt buộc PKCE S256.
- State được tạo ngẫu nhiên, lưu theo phiên và so sánh tại callback.
- Redirect URI khớp chính xác giữa đăng ký client, authorization request và token request.
- Authorization code được đổi một lần bằng đúng code verifier.
- Service client dùng CLIENT_SECRET_BASIC và Client Credentials grant.
- Secret service client được mã hóa khi lưu và được giữ ngoài frontend/repository.
- Hai client chỉ có scope cần thiết; Resource Server kiểm tra authority tương ứng.
- CORS dùng allowlist cho origin trình duyệt và không được xem là biện pháp thay thế PKCE.
- Token endpoint, issuer, signing key và Resource Server cùng tin cậy đúng cấu hình.
- Các ca âm cho PKCE, state, redirect URI, secret, scope và token hết hạn đều được kiểm tra.

Sau lab, ta có hai mẫu tích hợp OAuth 2.0 phù hợp với hai môi trường thực thi: public client bảo vệ authorization code bằng PKCE và client dịch vụ xác thực bằng secret ở backend. Cả hai đều nhận access token giới hạn theo scope và được Resource Server xác minh trước khi cho phép truy cập dữ liệu.
