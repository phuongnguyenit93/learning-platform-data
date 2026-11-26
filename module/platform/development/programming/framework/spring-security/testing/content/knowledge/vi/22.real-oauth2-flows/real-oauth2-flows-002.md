# Dùng endpoint giao thức trong hạ tầng kiểm thử do bộ test kiểm soát

## Mục tiêu học tập

Một bài test OAuth2/OIDC có thể dùng `oauth2Login()` hoặc `jwt()` để dựng principal và kiểm tra logic phía sau đăng nhập. Nhưng khi cần kiểm chứng redirect, token exchange, JWKS, UserInfo hoặc introspection, test phải gửi HTTP request đến các endpoint giao thức thực sự được ứng dụng cấu hình sử dụng.

Hạ tầng kiểm thử do bộ test kiểm soát giúp thực hiện việc đó mà không phụ thuộc vào một identity provider bên ngoài trong mọi lần chạy. Bộ test khởi động endpoint cục bộ, quyết định response, kiểm tra request mà ứng dụng gửi đến và dọn trạng thái sau mỗi kịch bản.

Sau bài học này, bạn có thể:

- Thiết kế một protocol fixture có endpoint discovery, authorization, token, JWKS, UserInfo, introspection và revocation khi flow cần.
- Dùng HTTP stub server để kiểm tra client gửi request OAuth2/OIDC đúng và xử lý response đúng.
- Dùng JWKS hoặc introspection endpoint cục bộ để kiểm tra resource server xác minh access token qua HTTP thật.
- Phân biệt endpoint giả lập do test điều khiển với authorization server thật chạy trong test container hoặc test realm.
- Kiểm tra các nhánh thành công, từ chối, timeout, response sai định dạng và key rotation.
- Cô lập port, key, client, user, session và dữ liệu giữa các test để tránh kết quả phụ thuộc thứ tự chạy.

Bài thuộc module **SPRING_SECURITY_TESTING**: kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Vì sao cần endpoint giao thức trong test?

Giả sử một ứng dụng Spring Security đăng nhập bằng OIDC. Khi người dùng truy cập trang được bảo vệ, ứng dụng redirect đến authorization endpoint, nhận callback có authorization code, gửi code đến token endpoint, xác minh ID token và tạo session.

Nếu test chỉ dùng `oidcLogin()`, principal đã được tạo sẵn. Test có thể xác minh trang hồ sơ hiển thị đúng tên, nhưng không kiểm tra:

- Authorization request có đúng `client_id`, `redirect_uri`, `scope` và `state` không.
- PKCE challenge có được gửi và verifier có được dùng khi đổi code không.
- Client có gọi đúng token endpoint và xác thực client đúng cách không.
- ID token có được xác minh theo issuer, audience, chữ ký và nonce không.
- Resource server có tải public key từ JWKS endpoint hoặc gọi introspection endpoint không.

Một protocol endpoint trong hạ tầng test tạo ra ranh giới HTTP thật: ứng dụng gửi request qua HTTP client của nó, còn test server nhận request và trả response theo kịch bản đã định nghĩa. Như vậy, ta kiểm tra được serialization, headers, form parameters, redirect và cách xử lý lỗi ở ranh giới giao thức.

### 1.1. Ba mức hạ tầng có thể kiểm soát

| Hạ tầng | Điều gì chạy thật? | Điều gì do test kiểm soát? | Dùng khi |
| --- | --- | --- | --- |
| HTTP stub server | HTTP client và protocol handling phía ứng dụng. | Response discovery, token, JWKS, UserInfo, introspection. | Cần test request/response và nhánh lỗi ổn định. |
| Authorization server test cục bộ | Authorization server và protocol endpoint thực của nó. | Container/process, client registration, user, key, clock và seed data. | Cần kiểm tra cả policy và việc cấp token của AS. |
| IdP sandbox/test realm | Provider thật trong môi trường test. | Client test, tài khoản test và một phần dữ liệu. | Cần xác nhận cấu hình hiện tại tương thích với provider bên ngoài. |

HTTP stub không phải authorization server hoàn chỉnh. Nó mô phỏng hợp đồng endpoint mà client hoặc resource server gọi. Nếu cần kiểm tra AS thực thi policy như redirect URI, PKCE, consent, code reuse hay refresh-token rotation, hãy chạy AS test thật hoặc test realm.

### 1.2. Sơ đồ hạ tầng test

~~~mermaid
flowchart LR
    T["JUnit test suite"] -->|start / configure| P["Protocol fixture"]
    C["Spring OAuth2 Client"] -->|HTTP authorize / token / userinfo| P
    R["Spring Resource Server"] -->|HTTP JWKS / introspection| P
    P -->|controlled responses| C
    P -->|controlled responses| R
    T -->|verify requests and state| P
    T -->|assert result| A["Application response / database"]
~~~

Fixture cần lắng nghe trên port động, cung cấp URL cho application context và lưu request journal để test xác minh ứng dụng đã gọi endpoint nào, với dữ liệu nào.

## 2. Chọn endpoint cần dựng theo flow

Không phải test nào cũng cần dựng tất cả endpoint. Hãy tạo đúng phần giao thức mà thành phần đang kiểm thử sử dụng.

| Endpoint | Vai trò | Test thường gặp |
| --- | --- | --- |
| `/.well-known/openid-configuration` | Công bố metadata OIDC: issuer, authorization endpoint, token endpoint, JWKS URI và endpoint khác. | Discovery và cấu hình provider. |
| `/oauth2/authorize` | Nhận authorization request và điều hướng người dùng/consent. | Client redirect, state, scope, PKCE challenge. |
| `/oauth2/token` | Đổi authorization code hoặc refresh token lấy token. | Grant type, client authentication, code verifier, token response. |
| `/oauth2/jwks` | Công bố public keys để xác minh JWT. | JWT signature, `kid`, key rotation. |
| `/userinfo` | Trả claims của người dùng cho access token hợp lệ. | Client gửi đúng access token và xử lý claims. |
| `/oauth2/introspect` | Trả trạng thái opaque token. | `active=true/false`, scope và client authentication. |
| `/oauth2/revoke` | Thu hồi token theo khả năng của AS. | Client gửi đúng token và xử lý kết quả revoke. |
| `/connect/logout` hoặc endpoint logout của provider | Kết thúc phiên đăng nhập ở provider. | Logout phối hợp, redirect sau logout. |

Tên path ở bảng là ví dụ phổ biến, không phải hằng số bắt buộc. Hãy lấy URL từ metadata hoặc cấu hình client registration. Với OAuth2 thuần không dùng OIDC, discovery endpoint OIDC có thể không tồn tại; client có thể được cấu hình authorization/token URI trực tiếp.

## 3. Khởi động HTTP protocol fixture trên port động

WireMock, MockWebServer hoặc một HTTP stub server tương đương đều có thể làm fixture. Ví dụ sau dùng WireMock để minh họa cách khởi động server, lấy base URL và reset trạng thái giữa các test.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

class ProtocolFixture implements AutoCloseable {

    private final WireMockServer server =
        new WireMockServer(wireMockConfig().dynamicPort());

    void start() {
        server.start();
    }

    String baseUrl() {
        return server.baseUrl();
    }

    WireMockServer server() {
        return server;
    }

    void reset() {
        server.resetAll();
    }

    @Override
    public void close() {
        if (server.isRunning()) {
            server.stop();
        }
    }
}
~~~

Trong test suite, fixture phải được khởi động trước khi Spring tạo bean phụ thuộc vào URL của nó. Với Spring Test, có thể dùng JUnit extension hoặc lifecycle tĩnh để start fixture trước khi `@DynamicPropertySource` cung cấp URL.

Ví dụ cách cung cấp issuer động:

~~~java
static final ProtocolFixture protocol = new ProtocolFixture();

static {
    protocol.start();
}

@DynamicPropertySource
static void oauthProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.security.oauth2.client.provider.test.issuer-uri",
        protocol::baseUrl
    );
}
~~~

Đây là khung minh họa. Trong dự án, bảo đảm fixture đã stub discovery metadata trước lần đầu Spring khởi tạo `ClientRegistration` hoặc `JwtDecoder`. Có thể gom start, stub và stop vào JUnit extension để tránh phụ thuộc thứ tự `static` initializer.

Không hardcode port như `8080` hoặc `9090`. Port động tránh xung đột khi chạy song song và khi developer đang chạy dịch vụ khác trên máy.

## 4. Stub discovery metadata và authorization endpoint

Với OIDC discovery, client lấy metadata từ issuer. Response phải nhất quán: trường `issuer` khớp issuer đã cấu hình, còn các endpoint phải trỏ về cùng fixture.

Ví dụ stub metadata:

~~~java
String issuer = protocol.baseUrl();

protocol.server().stubFor(get(urlEqualTo("/.well-known/openid-configuration"))
    .willReturn(okJson("""
        {
          "issuer": "%s",
          "authorization_endpoint": "%s/oauth2/authorize",
          "token_endpoint": "%s/oauth2/token",
          "jwks_uri": "%s/oauth2/jwks",
          "userinfo_endpoint": "%s/userinfo",
          "response_types_supported": ["code"],
          "subject_types_supported": ["public"],
          "id_token_signing_alg_values_supported": ["RS256"],
          "grant_types_supported": ["authorization_code", "refresh_token"],
          "token_endpoint_auth_methods_supported": ["client_secret_basic"]
        }
        """.formatted(issuer, issuer, issuer, issuer, issuer))));
~~~

Các trường metadata cần phản ánh khả năng thực sự của fixture và client. Không quảng bố grant type, thuật toán hoặc authentication method mà test server không hỗ trợ.

Khi client bắt đầu đăng nhập, test có thể gọi endpoint khởi tạo authorization của ứng dụng và đọc redirect URL:

~~~java
MvcResult result = mvc.perform(get("/oauth2/authorization/test"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

URI authorizationUri =
    URI.create(result.getResponse().getRedirectedUrl());
~~~

Sau đó parse query parameters và xác minh `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state` và các PKCE parameter khi được cấu hình.

Không chỉ kiểm tra chuỗi URL có chứa `state=`. Hãy parse URI để so sánh từng tham số, xác minh state không rỗng và không bị tái sử dụng giữa hai giao dịch. Với OIDC, kiểm tra `nonce` khi client gửi nó.

Authorization endpoint stub có thể chỉ ghi nhận request và để test tự mô phỏng bước người dùng chấp thuận. Cách này phù hợp để kiểm tra client. Nếu cần kiểm tra login, consent và policy của AS, dùng AS test thật thay cho một stub trả redirect cố định.

## 5. Kiểm tra callback và token endpoint bằng HTTP thật

Authorization Code flow có một ranh giới quan trọng: client nhận callback, kiểm tra giao dịch đang chờ và gửi code đến token endpoint.

Với Spring MVC, authorization request thường được lưu trong session. Test có thể giữ session từ request bắt đầu đăng nhập, rồi gửi callback vào đúng session đó.

~~~java
MvcResult start = mvc.perform(get("/oauth2/authorization/test"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) start.getRequest().getSession(false);

// state được parse từ URL redirect đã nhận ở bước trên.
String state = queryParameter(
    start.getResponse().getRedirectedUrl(), "state");

mvc.perform(get("/login/oauth2/code/test")
        .session(session)
        .param("code", "test-code-123")
        .param("state", state))
    .andExpect(status().is3xxRedirection());
~~~

Đoạn code là khung kiểm thử callback; helper `queryParameter(...)` cần parse URL-encoded query một cách đúng chuẩn. Với WebFlux, dùng `WebTestClient` và duy trì cookie/session giữa request bắt đầu đăng nhập và callback theo cấu hình ứng dụng.

Token endpoint stub cần kiểm tra request, không chỉ trả JSON thành công:

~~~java
protocol.server().stubFor(post(urlEqualTo("/oauth2/token"))
    .withRequestBody(containing("grant_type=authorization_code"))
    .withRequestBody(containing("code=test-code-123"))
    .willReturn(okJson("""
        {
          "access_token": "test-access-token",
          "token_type": "Bearer",
          "expires_in": 300,
          "scope": "orders.read"
        }
        """)));
~~~

Ví dụ trên dành cho OAuth2 client không yêu cầu ID token. Nếu registration yêu cầu OIDC scope `openid`, token response cần có ID token hợp lệ theo cấu hình kiểm tra của client. Không thể dùng một chuỗi JWT tùy ý: hãy ký ID token bằng private key test, công bố public key tương ứng ở JWKS, và tạo claims phù hợp như issuer, subject, audience, expiry và nonce.

Sau khi callback hoàn tất, xác minh token endpoint thực sự nhận:

- `grant_type=authorization_code`.
- Authorization code từ callback.
- Redirect URI phù hợp với giao dịch.
- PKCE `code_verifier` nếu client đã gửi challenge.
- Client authentication đúng phương thức đã đăng ký.
- Không có refresh token hoặc client secret bị gửi tới endpoint không liên quan.

WireMock có thể kiểm tra method, path, header và body. Ví dụ xác minh token exchange đã diễn ra:

~~~java
protocol.server().verify(postRequestedFor(urlEqualTo("/oauth2/token"))
    .withRequestBody(containing("grant_type=authorization_code"))
    .withRequestBody(containing("code=test-code-123")));
~~~

Một stub response thành công chỉ kiểm tra client xử lý response đó. Nó không kiểm tra AS có thực sự xác minh redirect URI, code reuse, PKCE hay consent. Các policy đó thuộc test của AS hoặc contract test với AS test thật.

## 6. Kiểm tra JWT và JWKS qua resource server

Đối với JWT access token, resource server phải gọi hoặc sử dụng key từ nguồn tin cậy để xác minh chữ ký. Một test tích hợp có thể chạy JWKS endpoint cục bộ, cấu hình `jwk-set-uri` của RS trỏ tới fixture và gửi bearer token đã ký bằng private key tương ứng.

Ví dụ cấu hình test:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: http://localhost:<dynamic-port>/oauth2/jwks
~~~

Không dùng nguyên văn placeholder trên trong YAML chạy được; test phải thay URL bằng base URL và port động do fixture cung cấp.

JWKS response có dạng JSON Web Key Set. Ví dụ một RSA public key test:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "test-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị modulus phải được tạo từ public key test thật. Không tự điền một modulus minh họa rồi kỳ vọng decoder xác minh được token.

Kịch bản nên có:

| Kịch bản | JWKS/token | Kỳ vọng |
| --- | --- | --- |
| Chữ ký hợp lệ | JWKS có public key tương ứng với private key ký token | RS xác thực được token. |
| Key ID lạ | Header `kid` không có trong JWKS | Token bị từ chối. |
| Chữ ký sai | Token ký bằng key khác | Token bị từ chối. |
| Issuer sai | Chữ ký đúng nhưng `iss` sai | Validator từ chối. |
| Audience sai | Chữ ký đúng nhưng `aud` không chứa API | Validator từ chối nếu policy yêu cầu audience. |
| Key rotation | JWKS được cập nhật với key mới | Decoder refresh/cache xử lý theo cấu hình. |
| JWKS timeout/5xx | Endpoint key lỗi hoặc không phản hồi | Authentication thất bại an toàn theo policy. |

Gửi token qua HTTP header:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedAccessToken))
    .andExpect(status().isOk());
~~~

Test này chạy bearer-token filter và decoder của ứng dụng. Khác với `jwt()`, nó kiểm tra đường xác minh token. `jwt()` vẫn hữu ích cho test authorization nhanh, nhưng không thay thế JWKS integration.

## 7. Kiểm tra opaque-token introspection qua endpoint cục bộ

Với opaque token, resource server gọi introspection endpoint để hỏi token có còn active hay không. Stub cần mô phỏng cả response và kiểm tra request mà RS gửi.

Response active:

~~~json
{
  "active": true,
  "sub": "user-42",
  "username": "linh",
  "scope": "orders.read",
  "client_id": "portal-test",
  "token_type": "Bearer"
}
~~~

Response inactive:

~~~json
{
  "active": false
}
~~~

Cấu hình test trỏ introspection URI đến fixture:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: http://localhost:<dynamic-port>/oauth2/introspect
          client-id: orders-api-test
          client-secret: test-only-secret
~~~

Tương tự JWKS, URL cần được cung cấp bằng dynamic property trong test context, không hardcode placeholder.

Stub active và inactive:

~~~java
protocol.server().stubFor(post(urlEqualTo("/oauth2/introspect"))
    .withRequestBody(containing("token=active-test-token"))
    .willReturn(okJson("""
        {
          "active": true,
          "sub": "user-42",
          "scope": "orders.read",
          "client_id": "portal-test"
        }
        """)));

protocol.server().stubFor(post(urlEqualTo("/oauth2/introspect"))
    .withRequestBody(containing("token=revoked-test-token"))
    .willReturn(okJson("""
        { "active": false }
        """)));
~~~

Gửi request tới API bằng bearer token và xác minh:

- Active token có scope cần thiết được chấp nhận.
- Active token thiếu scope nhận kết quả authorization bị từ chối.
- Inactive token không tạo authentication hợp lệ.
- RS gửi token đến đúng introspection endpoint.
- Client authentication được gửi theo cấu hình.
- Token không bị ghi vào log hoặc response lỗi.

Có thể verify HTTP Basic header hoặc form body tùy phương thức client authentication đã cấu hình. Đừng hardcode giả định mọi introspection client đều dùng cùng một phương thức.

`opaqueToken()` chỉ dựng principal giả lập cho test downstream authorization. Test gửi bearer token qua `OpaqueTokenIntrospector` thật mới kiểm tra HTTP introspection.

## 8. UserInfo, revocation và logout endpoint

Không phải mọi ứng dụng đều dùng các endpoint này, nhưng khi flow có sử dụng thì fixture nên mô phỏng chúng riêng.

### 8.1. UserInfo

UserInfo endpoint nhận access token và trả claims theo quyền được cấp. Test client nên xác minh:

- Gửi access token trong bearer header.
- Không gửi ID token thay access token.
- Xử lý response claims đúng với mapping của ứng dụng.
- Từ chối hoặc xử lý lỗi khi UserInfo trả `401`, `403` hoặc JSON không hợp lệ.
- Không ghi bearer token vào log.

Response UserInfo thường có subject (`sub`) để liên kết với danh tính đã xác thực. Nếu ứng dụng dùng OIDC, bảo đảm subject được xử lý theo hợp đồng và không ghép nhầm claims từ hai người dùng.

### 8.2. Revocation

Khi client hỗ trợ revoke token, stub endpoint có thể ghi nhận request revoke và trả response phù hợp với hợp đồng. Kiểm tra client gửi đúng token, token hint nếu có, client authentication và xử lý kết quả.

Một phản hồi thành công từ revocation endpoint không tự chứng minh resource server lập tức từ chối token đó nếu RS đang xác minh JWT offline. Với JWT tự xác minh, hiệu lực thu hồi có thể phụ thuộc TTL, denylist hoặc policy khác. Test cần kiểm tra kiến trúc revoke thực tế của hệ thống.

### 8.3. Logout

Logout local session và logout tại IdP là hai hành vi khác nhau. Nếu ứng dụng dùng OIDC RP-Initiated Logout, fixture có thể mô phỏng endpoint logout/discovery metadata và redirect sau logout. Test cần xác minh:

- Session/cookie local bị vô hiệu hóa.
- Redirect tới endpoint logout đúng nếu flow yêu cầu.
- `post_logout_redirect_uri` hợp lệ.
- `id_token_hint` chỉ được gửi khi policy yêu cầu và không bị lộ trong log.
- Trở lại ứng dụng không còn được xác thực bằng session cũ.

## 9. Tạo kịch bản lỗi có thể lặp lại

Lợi thế lớn của fixture là test có thể tái tạo chính xác response hiếm hoặc khó điều khiển từ IdP bên ngoài.

| Kịch bản | Cách fixture phản hồi | Điều cần assert |
| --- | --- | --- |
| Token endpoint timeout | Delay vượt timeout hoặc không trả response | Client xử lý timeout, không tạo session đăng nhập thành công. |
| Token endpoint 5xx | Trả HTTP 500 | Lỗi được xử lý, không log token/secret. |
| Token response thiếu `access_token` | JSON thiếu field bắt buộc | Client từ chối response không hợp lệ. |
| Token response `token_type` sai | Trả loại token không được hỗ trợ | Client không sử dụng token sai. |
| JWKS không có `kid` | Trả key set không chứa key cần thiết | JWT không được xác thực. |
| Introspection inactive | `active=false` | RS trả 401 theo entry point. |
| Introspection timeout | Stub delay hoặc connection failure | RS fail closed theo policy. |
| UserInfo 401 | Token không được chấp nhận | Client không dùng claims cũ như dữ liệu mới. |
| Callback state sai | Gửi state không khớp session | Client từ chối callback, không tạo authentication. |
| Code đổi lần hai | Token endpoint trả `invalid_grant` | Client không tạo authorized client từ code đã dùng. |

Khi kiểm tra timeout, đặt timeout test ngắn nhưng đủ ổn định, và xác minh không có retry vô hạn. Không dùng sleep dài tùy tiện; dùng delay được kiểm soát bởi stub và timeout rõ ràng.

## 10. Cô lập vòng đời và dữ liệu của protocol fixture

Fixture dùng chung có thể khiến test phụ thuộc thứ tự nếu không reset đúng cách. Áp dụng các nguyên tắc:

- Mỗi test suite hoặc test context có port động riêng.
- Reset stub mappings và request journal giữa các test khi cần.
- Dùng code, token, subject, client ID và key ID riêng theo kịch bản.
- Không chia sẻ authorization code hoặc state giữa các test.
- Giữ private key test ở fixture; chỉ public key được công bố qua JWKS.
- Dùng clock hoặc thời gian cố định có kiểm soát khi test `exp`, `nbf` và code expiry.
- Không chạy đồng thời hai test sửa cùng một mapping hoặc scenario state trên cùng server nếu chưa cô lập.
- Dừng server sau suite và giải phóng port.
- Không gọi IdP production hoặc đưa secret production vào fixture.

Nếu dùng Testcontainers để chạy authorization server thực, áp dụng lifecycle tương tự: container có health check, seed client/user, issuer URL động, key ổn định trong test run và cleanup dữ liệu sau khi hoàn tất.

## 11. Stub endpoint hay authorization server thật?

Chọn loại hạ tầng dựa trên câu hỏi cần trả lời:

| Câu hỏi | HTTP stub | AS test thật |
| --- | --- | --- |
| Client gửi đúng token request không? | Phù hợp; kiểm tra method, headers và body. | Có thể kiểm tra thêm. |
| Client xử lý token response lỗi/timeout không? | Rất phù hợp, dễ điều khiển. | Khó tạo một số tình huống hiếm hơn. |
| AS có từ chối redirect URI sai không? | Chỉ nếu tự viết logic stub; không chứng minh policy AS thật. | Phù hợp. |
| AS có kiểm tra PKCE và code reuse không? | Stub đơn giản không chứng minh điều này. | Phù hợp. |
| RS có gọi JWKS/introspection đúng không? | Phù hợp; verify request HTTP và response handling. | Cũng phù hợp, gần provider hơn. |
| Token do AS phát hành có được RS chấp nhận không? | Có thể ký bằng key test và mô phỏng JWKS. | Kiểm tra tích hợp hai thành phần thực tế hơn. |
| Login/consent/browser flow có đúng không? | Có thể mô phỏng redirect, nhưng không thay thế AS policy. | Phù hợp hơn cho integration/E2E. |

Stub tốt cho contract và fault-injection. AS test thật tốt cho protocol và policy. Sandbox provider tốt cho smoke test tương thích. Ba loại bổ sung cho nhau; không nên gắn nhãn stub response là “đã kiểm thử authorization server”.

## 12. Checklist trước khi chấp nhận protocol integration test

- Endpoint URL được lấy từ fixture động hoặc metadata, không hardcode port.
- Issuer trong discovery khớp chính xác issuer cấu hình.
- Client thực sự gửi HTTP request đến endpoint được kiểm tra.
- Test verify method, path, headers và body quan trọng.
- Callback giữ đúng session và kiểm tra state.
- PKCE verifier được kiểm tra khi flow yêu cầu.
- OIDC ID token có chữ ký test hợp lệ và nonce đúng nếu dùng OIDC.
- RS nhận bearer token qua HTTP và dùng decoder/introspector thật.
- Test có cả response thành công và lỗi có kiểm soát.
- Request journal/mapping được reset để test độc lập.
- Không có credential/token/secret thật trong source hoặc log.
- Báo cáo ghi rõ endpoint nào là stub, endpoint nào thuộc server thật.

## 13. Bài thực hành tổng hợp

Xây dựng một portal OAuth2 client và API resource server, sử dụng protocol fixture do test suite khởi động:

1. Start HTTP stub server trên port động trước khi Spring context được tạo.
2. Stub OIDC discovery metadata với issuer, authorization endpoint, token endpoint và JWKS URI nhất quán.
3. Gọi endpoint bắt đầu đăng nhập của portal; parse redirect và kiểm tra client ID, redirect URI, scope, state, PKCE challenge và nonce nếu có.
4. Giữ session, mô phỏng callback với code và state hợp lệ; xác minh client gọi token endpoint bằng authorization code và verifier tương ứng.
5. Thử state sai và xác minh callback bị từ chối, token endpoint không được gọi.
6. Cấu hình resource server dùng JWKS stub; gửi JWT đã ký bằng key test và xác minh token hợp lệ được chấp nhận.
7. Thử token ký bằng key khác hoặc có issuer/audience sai và xác minh bị từ chối.
8. Nếu ứng dụng hỗ trợ opaque token, stub introspection active/inactive và kiểm tra RS gọi endpoint thật.
9. Stub UserInfo/revocation/logout khi flow của ứng dụng sử dụng các endpoint đó.
10. Reset fixture giữa các test; chạy song song để kiểm tra không rò state, code hoặc mapping.
11. Chạy một smoke test riêng với AS test thật nếu cần chứng minh provider và policy tương thích.

**Tiêu chí hoàn thành:** test chứng minh ứng dụng đã gửi request đến đúng protocol endpoint, gửi đúng tham số, xử lý response thành công/lỗi đúng và không nhầm HTTP stub với authorization server thực.

## 14. Ghi nhớ

Protocol fixture biến các bước OAuth2/OIDC thành những tương tác HTTP có thể quan sát và điều khiển. Client có thể được kiểm tra qua authorization redirect, callback, token exchange, UserInfo và logout. Resource server có thể được kiểm tra qua JWKS hoặc introspection endpoint. Stub giúp kiểm soát response và lỗi; authorization server test thật giúp kiểm tra policy và token issuance thực tế.

`oauth2Login()`, `oidcLogin()`, `jwt()` và `opaqueToken()` vẫn hữu ích cho test logic sau khi principal đã được dựng. Khi cần bằng chứng về protocol, hãy gửi request qua HTTP client thật của ứng dụng đến endpoint trong hạ tầng test và verify cả request lẫn response.

Một protocol integration test đáng tin cậy cho biết **endpoint nào đã được gọi, thành phần nào đang chạy thật, response nào do test điều khiển và bước OAuth2/OIDC nào đã được chứng minh**.
