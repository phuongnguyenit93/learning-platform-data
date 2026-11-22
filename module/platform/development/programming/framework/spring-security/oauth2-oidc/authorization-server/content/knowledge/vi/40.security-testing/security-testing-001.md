# Negative test với redirect URI, scope, issuer và audience không hợp lệ

Một Authorization Server an toàn phải từ chối các authorization request và token không đáp ứng chính sách, đồng thời tránh chuyển hướng hoặc phát hành token cho đích không đáng tin cậy. Các lỗi như redirect URI sai, scope vượt quyền, issuer không đúng hoặc audience không dành cho API đích thường chỉ xuất hiện khi kiểm thử các đầu vào âm tính (negative tests).

Với Spring Authorization Server, cần kiểm tra cả nơi phát sinh lỗi lẫn nơi tiêu thụ token. Redirect URI và scope được kiểm tra trong quá trình xử lý authorization/client; issuer và audience còn phải được xác minh ở phía client hoặc Resource Server. Một token có chữ ký hợp lệ vẫn có thể không đáng tin nếu issuer hoặc audience sai.

## 1. Nguyên tắc thiết kế negative test

Một negative test tốt phải chứng minh được ba điều:

1. Đầu vào vi phạm một quy tắc bảo mật cụ thể.
2. Thành phần chịu trách nhiệm từ chối đúng đầu vào đó.
3. Không có tác dụng phụ nguy hiểm, chẳng hạn redirect tới host lạ, cấp scope vượt quyền hoặc chấp nhận token của issuer/resource khác.

Nên tạo dữ liệu kiểm thử riêng, gồm ít nhất một client hợp lệ, một client có scope giới hạn, một redirect URI đã đăng ký và một issuer/resource server dự kiến. Mỗi test chỉ nên thay đổi một yếu tố để biết chính xác quy tắc nào đang được kiểm tra.

| Nhóm kiểm thử | Thành phần chịu trách nhiệm chính | Kết quả cần chứng minh |
|---|---|---|
| Redirect URI | Authorization Server và RegisteredClient | Chỉ URI đã đăng ký mới được dùng làm đích trả authorization response |
| Scope | Authorization Server, consent và token policy | Client không thể xin hoặc nhận quyền vượt phạm vi được phép |
| Issuer | Client OIDC/OAuth2 và Resource Server | Token/metadata phải đến từ Authorization Server đã tin cậy |
| Audience | Resource Server hoặc OIDC client | Token chỉ được chấp nhận cho đúng API/client đích |

Không xem HTTP status là bằng chứng duy nhất. Một request bị từ chối có thể trả HTTP 400, 401 hoặc 403 tùy endpoint và security configuration. Hãy kiểm tra thêm OAuth error code, Location header, token claims, authorization state và việc không có token/credential bị phát hành.

## 2. Chuẩn bị fixture cho kiểm thử

Dùng RegisteredClient kiểm thử với các giá trị rõ ràng và cố định. Ví dụ:

~~~java
RegisteredClient webClient = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret("{noop}test-secret")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.test/callback")
        .scope(OidcScopes.OPENID)
        .scope("profile")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Đây là fixture minh họa cho test. Trong dự án thực tế, dùng PasswordEncoder và secret được cấu hình cho test, không dùng {noop} trong môi trường triển khai. Có thể tạo thêm client khác với redirect URI riêng hoặc scope ít hơn để kiểm tra ranh giới giữa các client.

Chuẩn bị các giá trị kiểm thử:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| Issuer được tin cậy | https://auth.example.test | Issuer mà client/resource server mong đợi |
| Redirect URI đã đăng ký | https://app.example.test/callback | Đích hợp lệ của authorization response |
| Redirect URI không hợp lệ | https://attacker.example/callback | Đầu vào cần bị từ chối |
| Scope được phép | openid profile orders.read | Quyền đã đăng ký cho client |
| Scope vượt quyền | admin.write | Quyền client không được cấp |
| Audience API | https://api.example.test | Resource server được phép nhận access token |
| Audience sai | https://other-api.example.test | Resource server khác |

Giữ private key, client secret và token test trong fixture an toàn. Không hardcode credential production vào source test. Nếu cần tạo JWT có claim sai, ký token bằng khóa test mà Resource Server tin cậy để kiểm tra riêng issuer/audience; nếu chữ ký cũng sai thì test sẽ thất bại vì lý do khác và không chứng minh được validator cần kiểm tra.

## 3. Negative test với redirect URI

Redirect URI xác định nơi Authorization Server gửi authorization response chứa authorization code hoặc lỗi. Nếu server chấp nhận URI do attacker kiểm soát, code có thể bị gửi tới hệ thống ngoài ý muốn. Vì vậy, server phải kiểm tra URI với danh sách đã đăng ký cho đúng client trước khi redirect.

Với RegisteredClient, Spring Authorization Server kiểm tra redirect URI theo giá trị đã đăng ký. Trong test, nên thử thay đổi riêng từng thành phần: scheme, host, port, path, query và fragment. Đừng dùng kiểm tra chuỗi kiểu startsWith trong custom validator để thay thế đối chiếu URI chính xác.

### 3.1 Các trường hợp cần kiểm tra

| Đầu vào | Vì sao không hợp lệ | Kết quả mong đợi |
|---|---|---|
| https://attacker.example/callback | Host không được đăng ký | Từ chối; không redirect tới attacker |
| http://app.example.test/callback | Scheme khác URI đã đăng ký | Từ chối với client web HTTPS |
| https://app.example.test:8443/callback | Port khác | Từ chối nếu port này không được đăng ký |
| https://app.example.test/other | Path khác | Từ chối |
| https://app.example.test/callback/ | Path có dấu slash cuối khác | Từ chối nếu không đăng ký chính xác |
| https://app.example.test.evil.test/callback | Host lookalike | Từ chối |
| https://app.example.test@attacker.example/callback | User-info làm host thực là attacker | Từ chối |
| URI chứa fragment | Fragment không phù hợp với redirect URI OAuth2 | Từ chối |
| URI thiếu hoặc bị thay đổi so với request ban đầu tại token endpoint | Không khớp authorization request | Token exchange thất bại |

Với native app, loopback redirect URI có thể có quy tắc port động theo hướng dẫn OAuth cho native applications. Không áp dụng máy móc fixture web HTTPS cho trường hợp loopback; hãy kiểm thử đúng quy tắc và cách hỗ trợ của phiên bản/thành phần client đang triển khai.

### 3.2 Kiểm tra Authorization Server không redirect tới URI lạ

Ví dụ request âm tính tới authorization endpoint:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fattacker.example%2Fcallback
    &scope=openid
~~~

Một kiểm thử MockMvc có thể xác minh URI lạ không xuất hiện trong Location header:

~~~java
mockMvc.perform(get("/oauth2/authorize")
        .param("response_type", "code")
        .param("client_id", "web-client")
        .param("redirect_uri", "https://attacker.example/callback")
        .param("scope", "openid"))
    .andExpect(status().isBadRequest())
    .andExpect(header().doesNotExist("Location"));
~~~

Đường dẫn endpoint và cách render lỗi có thể được tùy chỉnh trong ứng dụng. Điều kiện bảo mật quan trọng là response không được chuyển hướng tới URI không được xác minh. Nếu cấu hình ứng dụng trả một trang lỗi riêng, điều chỉnh assertion về status/body nhưng vẫn phải xác minh không có redirect tới host lạ.

Không nên kiểm tra rằng server redirect về URI đã đăng ký khi chính redirect URI trong request không hợp lệ. Theo quy tắc OAuth, nếu URI không được xác minh, Authorization Server không thể an toàn gửi error response tới URI đó.

### 3.3 Redirect URI hợp lệ nhưng scope sai

Đây là tình huống khác: redirect URI đã được xác minh, nhưng một tham số authorization khác không hợp lệ. Khi đó Authorization Server có thể gửi OAuth error response tới redirect URI hợp lệ theo quy tắc giao thức.

Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback
    &scope=openid%20admin.write
~~~

Test cần xác minh error là invalid_scope (hoặc mã lỗi theo extension/policy được triển khai), và nếu response được redirect thì Location phải trỏ đúng URI đã đăng ký. Không được có authorization code trong response.

### 3.4 Kiểm tra redirect_uri ở token endpoint

Sau khi có authorization code, client gửi token request kèm redirect_uri. Giá trị này phải khớp với URI trong authorization request ban đầu khi tham số được sử dụng theo authorization code flow.

Negative test nên:

1. Tạo authorization code bằng redirect URI hợp lệ.
2. Gửi token request với redirect URI khác, dù URI thay thế cũng nằm trong danh sách URI của client.
3. Xác minh token endpoint từ chối exchange theo quy tắc authorization code.
4. Xác minh không có access token hoặc refresh token được phát hành từ request sai.

Việc một URI khác cũng được đăng ký cho cùng client không làm nó trở thành URI đã dùng trong authorization request cụ thể đó.

## 4. Negative test với scope

Scope biểu thị quyền mà client yêu cầu. Authorization Server cần giới hạn scope theo RegisteredClient, yêu cầu người dùng consent khi chính sách cần, và không phát hành token có quyền vượt quá authorization đã được cấp.

Cần phân biệt ba lớp:

- **Requested scope**: scope client gửi trong authorization request hoặc token request.
- **Authorized scope**: scope thực sự được Authorization Server chấp thuận và lưu trong authorization.
- **Effective authority**: quyền Resource Server suy ra từ access token và policy của API.

Ba tập này có quan hệ nhưng không nhất thiết giống nhau. Ví dụ client xin openid profile orders.read, người dùng chỉ chấp thuận một tập nhỏ hơn theo chính sách, thì access token không được tự nhiên có thêm scope ngoài tập đã được cấp.

### 4.1 Scope không được đăng ký cho client

Đăng ký client chỉ cho openid, profile và orders.read, sau đó thử xin admin.write. Kiểm tra Authorization Server từ chối yêu cầu với invalid_scope hoặc lỗi tương ứng của endpoint. Không được tạo authorization code chứa scope vượt quyền.

Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback
    &scope=openid%20admin.write
~~~

Kiểm tra cả trường hợp scope hợp lệ nhưng bị viết sai, có khoảng trắng/encoding không đúng hoặc bị gửi lặp theo cách ứng dụng không hỗ trợ. Không tự động sửa tên scope gần giống nhau; orders.read và order.read là hai giá trị khác nhau.

### 4.2 Scope bị nâng quyền ở token endpoint

Với authorization code flow, token endpoint không được cấp quyền vượt quá authorization đã được cấp cho code. Tạo code với scope openid profile, sau đó thử yêu cầu thêm admin.write khi đổi code nếu endpoint/flow nhận tham số scope.

Với refresh token, nếu client yêu cầu scope mới, tập scope không được vượt quyền đã được cấp trong authorization gốc. Kiểm tra hành vi theo đúng grant và phiên bản đang dùng; nếu tham số scope bị từ chối, test xác minh invalid_scope hoặc invalid_grant theo semantics của implementation, đồng thời xác minh không có token mới với quyền nâng cao.

### 4.3 Kiểm tra consent không bị bỏ qua

Một client có thể được cấu hình yêu cầu consent. Test nên xác minh:

- Lần đầu xin scope mới thì consent UI xuất hiện theo policy.
- Sau khi user từ chối, Authorization Server không phát authorization code thành công.
- Consent cho client A không tự động trở thành consent cho client B.
- Scope chưa được chấp thuận không xuất hiện trong authorized scopes.
- Gỡ consent hoặc thay đổi quyền được phản ánh trong authorization request tiếp theo.
- Client không thể tự thêm scope bằng cách sửa request sau khi người dùng đã consent.

Consent là trạng thái gắn với principal và client. Không chỉ kiểm tra UI; hãy kiểm tra consent được lưu qua OAuth2AuthorizationConsentService và authorization thực tế được tạo qua OAuth2AuthorizationService.

### 4.4 Kiểm tra authority tại Resource Server

Resource Server thường ánh xạ scope thành authority như SCOPE_orders.read. Một test API cần xác minh token có orders.read được gọi endpoint yêu cầu quyền đó, trong khi token chỉ có profile bị từ chối.

Ví dụ với MockMvc và Spring Security Test, có thể kiểm tra policy endpoint bằng JWT giả lập trong unit/web-layer test; nhưng cần thêm integration test dùng token được Authorization Server phát hành để chứng minh scope claim và converter ánh xạ đúng trong toàn bộ luồng.

Không chỉ dựa vào scope string ở phía Authorization Server. Nếu Resource Server dùng custom JwtAuthenticationConverter, kiểm tra converter không vô tình cấp authority mặc định hoặc map một claim khác thành quyền quản trị.

## 5. Negative test với issuer

Issuer xác định Authorization Server đã phát hành token. Client và Resource Server phải biết issuer nào được tin cậy. Token có chữ ký hợp lệ nhưng iss sai vẫn phải bị từ chối.

Ví dụ issuer dự kiến:

~~~text
https://auth.example.test
~~~

Một token có thể được ký bằng khóa test đáng tin cậy nhưng chứa issuer khác:

~~~json
{
  "iss": "https://untrusted-issuer.example.test",
  "sub": "user-123",
  "aud": ["https://api.example.test"],
  "exp": 1893456000
}
~~~

Để test riêng issuer, ký JWT bằng cùng test key mà decoder tin cậy, chỉ thay claim iss. Nếu dùng khóa không tin cậy, decoder có thể từ chối chữ ký trước khi chạy issuer validator; kết quả đó không chứng minh kiểm tra issuer hoạt động.

### 5.1 Kiểm tra issuer ở Resource Server

Khi cấu hình Resource Server bằng issuer URI, Spring Security có thể lấy metadata/JWK và cấu hình kiểm tra issuer theo URI đã khai báo. Nếu tự tạo JwtDecoder, cần bảo đảm validator issuer được cấu hình rõ ràng.

Ví dụ:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.test";
    String jwkSetUri = "https://auth.example.test/oauth2/jwks";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

    return decoder;
}
~~~

Nếu decoder được cấu hình bằng JWK Set URI riêng, đừng giả định việc tải public key tự động xác minh issuer. JWK Set dùng để xác minh chữ ký; issuer là một claim cần được validator kiểm tra.

Test token với các giá trị sau:

- Issuer chính xác.
- Issuer khác hostname.
- Issuer khác scheme, ví dụ HTTP thay vì HTTPS.
- Issuer có path khác.
- Issuer có dấu slash cuối khác nếu không khớp định danh được cấu hình.
- Thiếu claim iss.

Kết quả mong đợi là decoder từ chối token không khớp issuer dự kiến.

### 5.2 Kiểm tra discovery metadata và issuer mismatch

OIDC discovery metadata công bố issuer và các endpoint. Client nên kiểm tra issuer trong metadata khớp issuer mà client đã cấu hình/đăng ký tin cậy. Nếu metadata trả issuer khác, client không nên tiếp tục sử dụng các endpoint/JWKS được công bố như thể đó là cùng một Authorization Server.

Trong hệ thống có nhiều instance, kiểm tra tất cả node trả cùng issuer. Reverse proxy, forwarded headers hoặc cấu hình base URL sai có thể khiến node công bố hostname nội bộ, scheme HTTP hoặc port không đúng.

Nếu triển khai issuer identification trong authorization response theo RFC 9207, bổ sung test cho tham số iss trả về ở authorization response và kiểm tra client so sánh nó với issuer dự kiến. Chỉ bật test này khi ứng dụng/client thực sự hỗ trợ cơ chế đó; không giả định mọi phiên bản Spring Authorization Server tự động bật extension.

## 6. Negative test với audience

Audience cho biết token được phát hành cho ai hoặc resource nào. Với access token, Resource Server cần xác minh token có được dành cho API mà nó đang bảo vệ hay không. Với OpenID Connect ID Token, aud xác định client nhận ID Token; không được nhầm audience của ID Token với audience của access token.

Ví dụ:

| Token | Audience mong đợi |
|---|---|
| Access token cho Orders API | https://api.example.test |
| Access token cho Billing API | https://billing.example.test |
| ID Token của web client | web-client (client_id) |

Một JWT có aud chứa Billing API không được chấp nhận tại Orders API chỉ vì nó được ký bởi cùng Authorization Server.

### 6.1 Audience validator cho Resource Server

Spring Resource Server mặc định xác minh các điều kiện JWT cơ bản như chữ ký và thời hạn; ứng dụng cần bổ sung validator audience theo resource server cụ thể nếu policy yêu cầu.

Ví dụ validator yêu cầu audience của Orders API phải xuất hiện trong claim:

~~~java
@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.example.test";
    String jwkSetUri = "https://auth.example.test/oauth2/jwks";
    String expectedAudience = "https://api.example.test";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "Required audience is missing",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator
            )
    );

    return decoder;
}
~~~

Các import cần thiết thuộc package Spring Security OAuth2 Resource Server/JWT. Đây là cấu hình minh họa cho một API; mỗi resource server cần dùng audience policy của chính nó. Nếu policy yêu cầu một audience duy nhất, hãy kiểm tra cả kích thước và nội dung của danh sách thay vì chỉ dùng contains.

### 6.2 Các trường hợp audience âm tính

| Claim aud | Resource Server | Kết quả |
|---|---|---|
| Chứa đúng audience của API | Orders API | Chấp nhận nếu các validator khác đạt |
| Chỉ chứa audience API khác | Orders API | Từ chối |
| Không có aud | Orders API | Từ chối nếu audience là bắt buộc |
| Audience là client ID thay vì API | Orders API | Từ chối nếu token cần dành cho API |
| Có nhiều audience | Orders API | Chấp nhận hoặc từ chối theo policy multi-audience |
| Audience bị sửa sau khi ký | Bất kỳ API nào | Chữ ký không hợp lệ, từ chối |

Để test audience validator, ký token bằng test key được decoder tin cậy và giữ issuer, thời hạn, subject hợp lệ; chỉ thay audience. Kiểm tra decoder ném lỗi validation và endpoint bảo vệ trả 401. Nếu token có chữ ký sai, test không cô lập được audience.

### 6.3 Audience của ID Token trong OIDC

OIDC client phải xác minh ID Token có aud chứa đúng client_id. Khi có nhiều audience, cần áp dụng quy tắc azp (authorized party) theo OpenID Connect Core; nếu azp xuất hiện, nó phải xác định đúng client liên quan. ID Token dành cho client A không được client B chấp nhận.

Negative tests cho ID Token nên bao gồm:

- aud không chứa client_id.
- aud chứa client_id khác.
- Nhiều audience nhưng azp thiếu trong trường hợp policy yêu cầu.
- azp không khớp client_id.
- iss sai hoặc nonce không khớp authorization request.
- exp, iat hoặc chữ ký không hợp lệ.

Nếu dùng thư viện OIDC client, ưu tiên kiểm tra bằng validator của thư viện và test end-to-end. Không chỉ decode ID Token rồi đọc JSON claim để quyết định đăng nhập thành công.

## 7. Ma trận negative test kết hợp

Một số lỗi chỉ được phát hiện khi kết hợp nhiều tham số. Hãy kiểm tra cả trường hợp một tham số sai và trường hợp request có nhiều sai sót để xác định server không làm rò rỉ dữ liệu hoặc chuyển hướng không an toàn.

| Test ID | Đầu vào sai | Điểm kiểm tra | Kết quả mong đợi |
|---|---|---|---|
| REDIR-01 | Host redirect URI không đăng ký | Authorization endpoint | Từ chối, không redirect tới host lạ |
| REDIR-02 | Scheme/port/path sai | Authorization endpoint | URI không được coi là URI hợp lệ |
| REDIR-03 | Redirect URI khác lúc đổi code | Token endpoint | Không phát hành token |
| REDIR-04 | URI chứa user-info/lookalike host | Authorization endpoint | Từ chối, không open redirect |
| SCOPE-01 | Scope không đăng ký | Authorization endpoint | invalid_scope hoặc lỗi policy tương ứng |
| SCOPE-02 | Scope nâng quyền khi đổi code/refresh | Token endpoint | Không cấp quyền vượt authorization gốc |
| SCOPE-03 | Token thiếu authority của API | Resource Server | 403 theo authorization policy |
| ISS-01 | JWT có issuer khác | JWT decoder | Token bị từ chối |
| ISS-02 | JWT thiếu issuer | JWT decoder | Token bị từ chối |
| ISS-03 | Discovery issuer không khớp cấu hình | OIDC client | Không tin metadata/endpoint sai issuer |
| AUD-01 | Access token dành cho API khác | Resource Server | 401 hoặc lỗi invalid token |
| AUD-02 | Access token thiếu audience bắt buộc | Resource Server | Từ chối |
| AUD-03 | ID Token không chứa client_id | OIDC client | Đăng nhập thất bại |
| AUD-04 | azp không khớp client_id | OIDC client | ID Token bị từ chối |

Với mỗi test, ghi lại request fixture, expected OAuth error hoặc HTTP result, và assertion về trạng thái sau request. Ví dụ, sau REDIR-01 không chỉ xác minh status mà còn xác minh không có authorization record/token được tạo và không có Location trỏ tới attacker.

## 8. Viết test với MockMvc và Spring Security

MockMvc phù hợp để kiểm tra endpoint và security chain trong cùng application context. Ví dụ test redirect URI sai có thể được viết như sau:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationNegativeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsUnregisteredRedirectUriWithoutRedirecting() throws Exception {
        mockMvc.perform(get("/oauth2/authorize")
                .param("response_type", "code")
                .param("client_id", "web-client")
                .param("redirect_uri",
                        "https://attacker.example/callback")
                .param("scope", "openid"))
            .andExpect(status().isBadRequest())
            .andExpect(header().doesNotExist("Location"));
    }
}
~~~

Đường dẫn endpoint, trạng thái HTTP và cách render lỗi có thể thay đổi theo cấu hình ứng dụng. Điều không được thay đổi là không redirect tới URI chưa xác minh. Nếu test cần đăng nhập, cấu hình principal test bằng Spring Security Test hoặc thực hiện login flow theo cách ứng dụng đang dùng.

Với scope không hợp lệ và redirect URI hợp lệ, kiểm tra OAuth error response theo giao thức. Tùy cách endpoint xử lý, lỗi có thể được redirect về URI hợp lệ với query error=invalid_scope hoặc được render theo cấu hình. Không buộc mọi endpoint phải có cùng status code.

Đối với issuer và audience, nên kiểm tra JwtDecoder trực tiếp trong test tích hợp và thêm một test endpoint được bảo vệ để chứng minh request bị chặn tại Resource Server. Sử dụng token ký bằng test key đáng tin cậy, có thể điều chỉnh claim để mỗi test chỉ kiểm tra một validator.

## 9. Các lỗi trong chính bộ negative test

Negative test cũng có thể cho kết quả sai nếu fixture không cô lập đúng điều kiện:

- Token hết hạn trước khi test issuer hoặc audience; test chỉ chứng minh kiểm tra thời hạn.
- Chữ ký token sai khi đang kiểm tra iss hoặc aud; test chỉ chứng minh kiểm tra chữ ký.
- Client không được đăng ký grant type; test scope thất bại từ bước client authorization.
- Redirect URI không hợp lệ cùng lúc scope sai; server dừng ở redirect validation nên chưa kiểm tra scope.
- Test dùng mock JwtDecoder luôn trả token hợp lệ; không kiểm tra validator thật.
- Database/cache còn dữ liệu từ test trước, khiến consent hoặc authorization ảnh hưởng kết quả.
- Test chỉ assert HTTP 400 mà không kiểm tra Location, token hoặc authorization state.

Dùng một test riêng cho từng quy tắc, sau đó mới bổ sung test kết hợp. Khi một test thất bại, đọc error code và assertion cụ thể trước khi sửa. Không nới lỏng validator chỉ để làm cho test xanh.

## 10. Tiêu chí bảo mật và báo cáo kết quả

Bộ negative test đạt khi chứng minh được:

1. Redirect URI không hợp lệ không nhận authorization response, authorization code hoặc token.
2. Scope không được phép không thể được xin, consent hoặc phát hành vượt policy.
3. Token từ issuer không được tin cậy bị từ chối dù chữ ký có thể hợp lệ theo khóa test.
4. Access token có audience không phù hợp bị Resource Server từ chối.
5. ID Token không dành cho client hiện tại bị OIDC client từ chối.
6. Các lỗi không làm lộ raw token, authorization code, client secret hoặc dữ liệu xác thực.
7. Kết quả ổn định khi test chạy lặp lại và trên cấu hình gần production.

Báo cáo nên nêu test ID, thành phần được kiểm tra, đầu vào âm tính, kết quả thực tế, kết quả mong đợi và bằng chứng không có tác dụng phụ. Dùng correlation ID, client ID và authorization ID nội bộ để truy vết; không đưa giá trị credential vào log hoặc artifact.

Negative testing cho redirect URI, scope, issuer và audience giúp xác minh các ranh giới tin cậy quan trọng nhất trong OAuth 2.0/OpenID Connect. Khi mỗi validator được kiểm tra độc lập và kết quả được xác nhận ở cả Authorization Server lẫn Resource Server, đội phát triển có thể phát hiện sớm lỗi cấu hình dẫn tới open redirect, privilege escalation hoặc chấp nhận token sai đích.

